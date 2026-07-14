from datetime import timedelta
from gettext import gettext as _

from django.conf import settings
from django.core.management import BaseCommand, CommandError
from django.db import connections
from django.db.migrations.executor import MigrationExecutor
from django.db.utils import OperationalError
from django.utils.timezone import now

from pulpcore.app.domain_move import (
    DomainMoveError,
    copy_domain_data,
    domain_move_lock,
    estimate_domain_size,
    verify_domain_data,
)
from pulpcore.app.models import Domain, DomainMove, Task
from pulpcore.constants import TASK_INCOMPLETE_STATES

#: Default length of the Step 6 "Monitoring" window (design doc: "Observe for N days
#: (configurable, default 7)").
DEFAULT_MONITORING_DAYS = 7


class Command(BaseCommand):
    """
    Move a domain's data-plane objects to a different `DATABASES` alias.

    Implements Strategy A ("Read-Only Cutover") from the design doc's Domain Movement
    Procedure: the domain is set read-only (`Domain.moving = True`) for the duration of the
    data copy, which is simpler to implement than Strategy B's incremental sync but leaves the
    domain unavailable for writes for the whole copy -- acceptable for the moderate-sized
    domains this tooling targets, and the only strategy implemented by this command (Strategy B
    remains "backburner" per the design doc; passing `--strategy incremental` fails fast with a
    clear message rather than silently falling back to Strategy A).

    Steps 1-6 of the procedure are all handled by a single invocation of this command:
    preparation/verification, read-only mode, data copy (Option B -- application-level Django
    read+write; see `pulpcore.app.domain_move`), verification (row counts + checksums), cutover,
    and recording the Step 6 monitoring window on a new `DomainMove` row. Step 7 (cleanup of the
    stale rows left on the original alias) is a separate, deliberately more cautious command:
    `cleanup-moved-domain`.
    """

    help = __doc__

    def add_arguments(self, parser):
        parser.add_argument("domain", help=_("Name of the domain to move."))
        parser.add_argument(
            "--to",
            required=True,
            dest="to_alias",
            help=_("Target DATABASES alias to move the domain's data to."),
        )
        parser.add_argument(
            "--strategy",
            default="read-only",
            choices=["read-only", "incremental"],
            help=_(
                "Movement strategy. Only 'read-only' (Strategy A) is implemented; 'incremental' "
                "(Strategy B) remains on the backburner in the design doc pending a sync-"
                "strategy decision."
            ),
        )
        parser.add_argument(
            "--skip-copy",
            action="store_true",
            help=_(
                "Skip the data-copy step, assuming the domain's data was already copied to the "
                "target alias out-of-band (e.g. via pg_dump/postgres_fdw, see the module "
                "docstring in pulpcore.app.domain_move). Verification and cutover still run."
            ),
        )
        parser.add_argument(
            "--monitoring-days",
            type=int,
            default=DEFAULT_MONITORING_DAYS,
            help=_(
                "Length, in days, of the Step 6 monitoring window recorded on the DomainMove "
                "row. Default: %(default)s."
            ),
        )
        parser.add_argument(
            "--noinput",
            "--no-input",
            action="store_false",
            dest="interactive",
            help=_("Do not prompt for confirmation before starting the move."),
        )

    def handle(self, *args, **options):
        if options["strategy"] == "incremental":
            raise CommandError(
                _(
                    "Strategy B (incremental sync) is not implemented -- see the 'Domain "
                    "Movement Procedure' section of architecture/domain-db-offloading-design.md. "
                    "Use --strategy read-only."
                )
            )

        to_alias = options["to_alias"]
        if to_alias not in settings.DATABASES:
            raise CommandError(
                _("'{alias}' is not a configured DATABASES alias.").format(alias=to_alias)
            )

        try:
            domain = Domain.objects.using("default").get(name=options["domain"])
        except Domain.DoesNotExist:
            raise CommandError(_("No domain named '{name}' exists.").format(name=options["domain"]))

        self._validate_preconditions(domain, to_alias)

        size_report = estimate_domain_size(domain, domain.database_alias)
        self._print_size_report(domain, size_report)

        if options["interactive"]:
            confirm = input(
                _(
                    "This will make domain '{name}' read-only for the duration of the copy "
                    "(may take a long time for large domains) and then move its data from "
                    "'{source}' to '{target}'. Continue? [y/N]: "
                ).format(name=domain.name, source=domain.database_alias, target=to_alias)
            )
            if confirm.strip().lower() not in ("y", "yes"):
                self.stdout.write(_("Aborted."))
                return

        with domain_move_lock():
            self._move(domain, to_alias, options)

    def _validate_preconditions(self, domain, to_alias):
        if domain.name == "default":
            raise CommandError(
                _(
                    "The 'default' domain can never be moved -- it is the only domain "
                    "guaranteed to exist on every deployment, and bootstrap/migration code "
                    "throughout pulpcore assumes it is reachable without any domain context."
                )
            )
        if domain.moving:
            raise CommandError(
                _(
                    "Domain '{name}' already has moving=True -- either another move is in "
                    "progress (check for a concurrent 'move-domain' run) or a previous move "
                    "was interrupted. Resolve manually (inspect the latest DomainMove row for "
                    "this domain) before retrying."
                ).format(name=domain.name)
            )
        if domain.database_alias == to_alias:
            raise CommandError(
                _("Domain '{name}' is already on alias '{alias}'.").format(
                    name=domain.name, alias=to_alias
                )
            )

        self._validate_alias_ready(to_alias)

        incomplete = Task.objects.using("default").filter(
            pulp_domain=domain, state__in=TASK_INCOMPLETE_STATES
        )
        if incomplete.exists():
            raise CommandError(
                _(
                    "Domain '{name}' has {n} in-flight task(s) (waiting/running/canceling). "
                    "Wait for them to finish (or cancel them) before moving this domain -- "
                    "read-only mode does not preempt already-dispatched work."
                ).format(name=domain.name, n=incomplete.count())
            )

    def _validate_alias_ready(self, alias):
        try:
            connections[alias].ensure_connection()
        except OperationalError as e:
            raise CommandError(
                _("Target alias '{alias}' is not reachable: {error}").format(alias=alias, error=e)
            ) from e
        executor = MigrationExecutor(connections[alias])
        targets = executor.loader.graph.leaf_nodes()
        if executor.migration_plan(targets):
            raise CommandError(
                _(
                    "Target alias '{alias}' has pending migrations. Run 'pulpcore-manager "
                    "migrate-all' first."
                ).format(alias=alias)
            )

    def _print_size_report(self, domain, size_report):
        self.stdout.write(_("Size estimate for domain '{name}':").format(name=domain.name))
        for row in size_report:
            if row["row_count"] == 0:
                continue
            self.stdout.write(
                "  {model}: {rows} row(s) (table total size: {size} bytes)".format(
                    model=row["model"], rows=row["row_count"], size=row["table_total_size_bytes"]
                )
            )

    def _move(self, domain, to_alias, options):
        from_alias = domain.database_alias
        move = DomainMove.objects.using("default").create(
            domain=domain, from_alias=from_alias, to_alias=to_alias, started_at=now()
        )
        try:
            # Step 2 -- read-only mode. Deliberately NOT skip_hooks: the post_save signal in
            # domain_sync.py must fire so every satellite (including `to_alias`, before any data
            # even lands there) sees moving=True too -- DomainMiddleware/PulpcoreWorker consult
            # the ContextVar-cached copy of this row on whichever alias/process they happen to
            # be running against, not necessarily `default`.
            domain.moving = True
            domain.save(update_fields=["moving"])

            if options["skip_copy"]:
                self.stdout.write(
                    self.style.WARNING(
                        _(
                            "--skip-copy given: assuming data was already copied to '{alias}'."
                        ).format(alias=to_alias)
                    )
                )
            else:
                self.stdout.write(
                    _("Copying data from '{source}' to '{target}'...").format(
                        source=from_alias, target=to_alias
                    )
                )
                copied = copy_domain_data(domain, from_alias, to_alias)
                for label, count in copied.items():
                    if count:
                        self.stdout.write(f"  {label}: {count} row(s) copied")

            self.stdout.write(_("Verifying copied data..."))
            mismatches = verify_domain_data(domain, from_alias, to_alias)
            if mismatches:
                for m in mismatches:
                    self.stderr.write(
                        self.style.ERROR(
                            "  {model}: source={source_count} rows (checksum "
                            "{source_checksum}), target={target_count} rows (checksum "
                            "{target_checksum})".format(**m)
                        )
                    )
                raise DomainMoveError(
                    "Verification failed for {n} model(s); see above. Domain '{name}' left "
                    "read-only on its original alias ('{alias}') -- no cutover performed. Fix "
                    "the discrepancy (e.g. re-run without --skip-copy) and retry.".format(
                        n=len(mismatches), name=domain.name, alias=from_alias
                    )
                )

            # Step 5 -- cutover.
            domain.database_alias = to_alias
            domain.moving = False
            domain.save(update_fields=["database_alias", "moving"])

            cutover_at = now()
            move.cutover_at = cutover_at
            move.monitoring_until = cutover_at + timedelta(days=options["monitoring_days"])
            move.status = "completed"
            move.save(update_fields=["cutover_at", "monitoring_until", "status"])

            self.stdout.write(
                self.style.SUCCESS(
                    _(
                        "Domain '{name}' moved from '{source}' to '{target}'. Monitor until "
                        "{until} before running 'cleanup-moved-domain {name}' (DomainMove "
                        "{move_id})."
                    ).format(
                        name=domain.name,
                        source=from_alias,
                        target=to_alias,
                        until=move.monitoring_until,
                        move_id=move.pk,
                    )
                )
            )
        except Exception as e:
            move.status = "failed"
            move.error = str(e)
            move.save(update_fields=["status", "error"])
            # Always clear moving=True on failure -- an admin re-running the command (or just
            # using the domain read-only in the meantime) needs writes to work again; the
            # original alias still has the authoritative (unmodified, since we only ever copy
            # *to* the target, never delete from the source until 'cleanup-moved-domain') data,
            # so clearing it is always safe regardless of how far the copy/verify got.
            if domain.moving:
                domain.moving = False
                domain.save(update_fields=["moving"])
            if isinstance(e, DomainMoveError):
                raise CommandError(str(e)) from e
            raise
