from contextlib import contextmanager
from gettext import gettext as _

from django.conf import settings
from django.core.management import BaseCommand, CommandError, call_command
from django.db import connections
from django.utils.timezone import now

from pulpcore.app.models import MigrationStatus
from pulpcore.constants import MIGRATION_ORCHESTRATOR_LOCK

DOMAIN_TABLE_CHECKPOINT = ["core"]


@contextmanager
def _orchestrator_lock():
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
    Migrate every configured database alias, in the correct order.

    Runs Django's migrate command once for each alias in DATABASES, migrating the
    default alias first so that satellite aliases can bootstrap against it. Safe to
    re-run; already-migrated aliases are simply no-ops.
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
            ordered_aliases = aliases + ["default"]
        else:
            ordered_aliases = ["default"] + aliases

        with _orchestrator_lock():
            for alias in ordered_aliases:
                if alias == "default":
                    self._migrate_one(alias, target)
                    if not target:
                        self._sync_domains()
                elif target:
                    self._migrate_one(alias, target)
                else:
                    self._migrate_satellite_forward(alias)

    def _migrate_satellite_forward(self, alias):
        self._migrate_one(alias, DOMAIN_TABLE_CHECKPOINT, record_status=False)
        self._sync_domains(alias=alias)
        self._migrate_one(alias, None)

    def _migrate_one(self, alias, target, record_status=True):
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
            self.stderr.write(
                self.style.WARNING(
                    _(
                        "Domain sync to satellite '{alias}' failed; continuing with satellite "
                        "migrations. Run 'pulpcore-manager sync-domains' manually afterwards."
                    ).format(alias=alias or "*")
                )
            )
