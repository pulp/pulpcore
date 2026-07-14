from contextlib import contextmanager
from gettext import gettext as _

from django.conf import settings
from django.core.management import BaseCommand, CommandError, call_command
from django.db import connections
from django.utils.timezone import now

from pulpcore.app.models import MigrationStatus
from pulpcore.constants import MIGRATION_ORCHESTRATOR_LOCK

#: A brand new satellite's forward migration is split into two `migrate` invocations around
#: this checkpoint -- see `_migrate_satellite_forward` for why neither a single uninterrupted
#: `migrate` run nor `sync-domains` alone can bootstrap a satellite correctly. This must be the
#: whole `core` app (not just the migration that first creates `core_domain`, e.g.
#: `0101_add_domain`): `Domain`'s schema keeps changing in later `core` migrations too (e.g.
#: `0128_domain_pulp_labels`, `0154_domain_database_alias_domain_moving`), and `sync-domains`
#: reads/writes `Domain` through the live ORM model -- which reflects *all* of those fields --
#: so the satellite's `core_domain` table must already match that full, current schema before
#: `sync-domains` can query it, not just exist.
DOMAIN_TABLE_CHECKPOINT = ["core"]


@contextmanager
def _orchestrator_lock():
    """
    Hold a PostgreSQL session-level advisory lock on `default` for the duration of a
    `migrate-all` run, so two orchestration runs (e.g. two pods restarting at once, or a second
    invocation while one is already in progress) can't race each other across `DATABASES`
    aliases. Fails fast (rather than blocking) if the lock is already held -- an operator
    re-running `migrate-all` while one is already in progress should see a clear error, not hang.

    Session-level (not transaction-level): released automatically if the holding connection
    drops (e.g. the pod running this command crashes), matching the design doc's failure-mode
    table ("Pod crashes mid-migrate-all: Advisory lock released on disconnect").
    """
    with connections["default"].cursor() as cursor:
        cursor.execute("SELECT pg_try_advisory_lock(%s)", [MIGRATION_ORCHESTRATOR_LOCK])
        (acquired,) = cursor.fetchone()
        if not acquired:
            raise CommandError(
                _(
                    "Could not acquire the migration-orchestrator advisory lock. Another "
                    "'migrate-all' run is already in progress."
                )
            )
        try:
            yield
        finally:
            cursor.execute("SELECT pg_advisory_unlock(%s)", [MIGRATION_ORCHESTRATOR_LOCK])


class Command(BaseCommand):
    """
    Migrate every configured `DATABASES` alias, in the correct order.

    Every RDS instance -- `default` and every satellite -- runs an identical Django schema
    (accepted trade-off, see KI-16 in the design doc), so `allow_migrate` never has to reason
    about which tables "belong" on which alias; this command just runs Django's own `migrate`
    once per alias, in an order that respects the one real cross-alias dependency: satellite
    bootstrap logic (e.g. `get_domain_pk()`'s default-domain lookup, run as a migration default
    via `Domain.objects.using(<satellite>)` reads) can depend on the `Domain` table already
    being current, so `default` -- where `Domain` is authoritative -- always migrates first on
    the way forward. Each satellite's own forward migration is further split around the
    migration that first creates `core_domain` (see `_migrate_satellite_forward`), with a
    `sync-domains --alias=<that satellite>` in between, so its `Domain` row exists before any
    later migration or post_migrate hook on that satellite needs to FK against it. Rollback
    (`--target`) reverses the alias ordering -- satellites roll back first, `default` last, so
    `default`'s schema (and the `Domain` table specifically) is never older than any satellite's
    expectation of it while a rollback is in progress -- but does not need the same split, since
    rolling back never needs to create new FK-referencing rows.

    Safe to re-run: already-migrated aliases are no-ops for Django's own `migrate`, and a
    partial failure only affects the alias it failed on -- aliases already handled in this run
    (or a previous one) are unaffected. See `MigrationStatus` for a durable per-alias record of
    the last outcome (also surfaced on the `/status/` endpoint).
    """

    help = __doc__

    def add_arguments(self, parser):
        parser.add_argument(
            "--target",
            nargs=2,
            metavar=("APP", "MIGRATION"),
            help=_(
                "Roll back every alias to this migration (Django 'app migration_name' syntax, "
                "e.g. 'core 0154'). Without --target, migrates every alias to its latest "
                "migration."
            ),
        )

    def handle(self, *args, **options):
        target = options.get("target")
        aliases = [alias for alias in settings.DATABASES if alias != "default"]
        if target:
            # Rollback ordering: satellites first, `default` last.
            ordered_aliases = aliases + ["default"]
        else:
            # Forward ordering: `default` first (authoritative Domain table + control plane).
            ordered_aliases = ["default"] + aliases

        with _orchestrator_lock():
            for alias in ordered_aliases:
                if alias == "default":
                    self._migrate_one(alias, target)
                    if not target:
                        # Populate satellites' Domain rows once `default`'s own Domain table is
                        # current: a satellite migration's data defaults (e.g. `get_domain_pk()`)
                        # may need to resolve a `Domain` row on that satellite already.
                        self._sync_domains()
                elif target:
                    # Rollback: no bootstrap dance needed, just roll back like any other alias.
                    self._migrate_one(alias, target)
                else:
                    self._migrate_satellite_forward(alias)

    def _migrate_satellite_forward(self, alias):
        """
        Forward-migrate one brand new (or partially migrated) satellite alias.

        Split into two `migrate` invocations around the point where `core_domain` starts to
        exist, because a single uninterrupted `migrate --database=<alias>` run can't satisfy
        both ordering constraints at once:

        * `sync-domains` needs `alias` to already have a `core_domain` table matching the live
          `Domain` model's full current schema, so it can read/write through the ORM -- only
          true once the whole `core` app is migrated on `alias` (see `DOMAIN_TABLE_CHECKPOINT`).
        * Every app's post_migrate hooks -- including this satellite's own, e.g.
          `_populate_artifact_serving_distribution` (KI-24), which is deliberately unguarded so
          it runs on every alias -- fire once *all* apps finish migrating, and can create
          data-plane rows that FK to `Domain`; they need the `Domain` *row* (not just the table)
          already replicated to `alias` by then, i.e. before any plugin app's migrations run.

        So: migrate only as far as the checkpoint, reconcile just this one alias (other,
        not-yet-migrated satellites may not have a `core_domain` table yet either, hence
        `--alias` rather than a full `sync-domains` sweep), then finish the rest.
        """
        self._migrate_one(alias, DOMAIN_TABLE_CHECKPOINT, record_status=False)
        self._sync_domains(alias=alias)
        self._migrate_one(alias, None)

    def _migrate_one(self, alias, target, record_status=True):
        # Note: no "running" pre-write here. `MigrationStatus` itself lives in the `core` app's
        # migrations, so on a genuinely fresh alias (first-ever bootstrap of a brand new `default`,
        # or a satellite's very first `migrate-all` run) `core_migrationstatus` doesn't exist
        # *yet* -- writing to it before `call_command("migrate", ...)` has had a chance to create
        # it would itself fail. Only write status after the migrate attempt, by which point the
        # table exists on `alias` regardless of outcome (`migrate` creates tables before running
        # any RunPython data migrations that could fail).
        self.stdout.write(_("Migrating database alias '{alias}'...").format(alias=alias))
        args = ["migrate", "--database", alias, "--noinput"]
        if target:
            args.extend(target)
        try:
            call_command(*args)
        except Exception as e:
            if record_status:
                self._record_status(alias, "failed", error=str(e))
            raise CommandError(
                _("Migration failed for database alias '{alias}': {error}").format(
                    alias=alias, error=e
                )
            ) from e
        else:
            if record_status:
                self._record_status(alias, "complete", completed_at=now())
                self.stdout.write(
                    self.style.SUCCESS(_("Database alias '{alias}' migrated.").format(alias=alias))
                )

    def _record_status(self, alias, status, **defaults):
        defaults.setdefault("error", None)
        try:
            MigrationStatus.objects.update_or_create(
                database_alias=alias, defaults={"status": status, **defaults}
            )
        except Exception:
            # Best-effort bookkeeping only -- never let a MigrationStatus write failure mask
            # the actual migration outcome above.
            self.stderr.write(
                self.style.WARNING(
                    _("Could not record MigrationStatus for alias '{alias}'.").format(alias=alias)
                )
            )

    def _sync_domains(self, alias=None):
        try:
            if alias:
                call_command("sync-domains", alias=alias)
            else:
                call_command("sync-domains")
        except Exception:
            # Best-effort: `sync-domains` can be re-run manually, and a satellite that's
            # unreachable right now for reconciliation will simply be migrated in its
            # then-current (possibly Domain-stale) state -- not fatal to the orchestration run.
            self.stderr.write(
                self.style.WARNING(
                    _(
                        "Domain sync to satellite '{alias}' failed; continuing with satellite "
                        "migrations. Run 'pulpcore-manager sync-domains' manually afterwards."
                    ).format(alias=alias or "*")
                )
            )
