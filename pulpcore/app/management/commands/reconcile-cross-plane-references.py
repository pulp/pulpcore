from gettext import gettext as _

from django.conf import settings
from django.core.management import BaseCommand

from pulpcore.app.tasks.reconciliation import reconcile_cross_plane_references


class Command(BaseCommand):
    """
    KI-11: sweep for orphaned cross-plane `GenericForeignKey` references.

    Checks every `CreatedResource`/`ExportedResource`/`UserRole`/`GroupRole` row that records a
    cross-plane target (a `content_object` living on a different alias than the row itself, per
    the KI-18 `content_object_domain` field) and reports any whose target can no longer be
    resolved on its recorded alias -- e.g. because the referencing task crashed before its
    data-plane write landed (no distributed transactions, see the design doc's KI-11), or because
    a domain was moved/cleaned-up while the row still pointed at the old alias.

    Safe to run at any time, including on a single-database deployment (there are no cross-plane
    rows to find, so it's a fast no-op). Intended to also run periodically via a `TaskSchedule`
    (see `pulpcore.app.util.configure_cleanup`); this command exists for on-demand/manual runs and
    for operators who want a report without waiting for the next scheduled sweep.
    """

    help = __doc__

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help=_("Report orphans without purging any of them, regardless of --purge-after-days."),
        )
        parser.add_argument(
            "--grace-period-minutes",
            type=int,
            default=None,
            help=_(
                "Skip rows updated more recently than this many minutes ago. Defaults to "
                "settings.CROSS_PLANE_RECONCILIATION_GRACE_MINUTES (currently {default})."
            ).format(default=settings.CROSS_PLANE_RECONCILIATION_GRACE_MINUTES),
        )
        parser.add_argument(
            "--purge-after-days",
            type=int,
            default=None,
            help=_(
                "Delete confirmed-orphaned rows older than this many days. 0 disables purging "
                "(the default). Defaults to settings.CROSS_PLANE_RECONCILIATION_PURGE_AFTER_DAYS "
                "(currently {default})."
            ).format(default=settings.CROSS_PLANE_RECONCILIATION_PURGE_AFTER_DAYS),
        )

    def handle(self, *args, **options):
        report = reconcile_cross_plane_references(
            grace_period_minutes=options["grace_period_minutes"],
            purge_after_days=options["purge_after_days"],
            dry_run=options["dry_run"],
        )

        self.stdout.write(
            _("Checked {checked} cross-plane row(s); found {orphaned} orphan(s).").format(
                checked=report["checked"], orphaned=report["orphaned"]
            )
        )
        for orphan in report["orphans"]:
            self.stdout.write(
                self.style.WARNING(
                    "  {model} pk={pk} (recorded alias='{alias}', age={age}d)".format(
                        model=orphan["model"],
                        pk=orphan["pk"],
                        alias=orphan["alias"],
                        age=orphan["age_days"],
                    )
                )
            )
        if report["purged"]:
            self.stdout.write(
                self.style.SUCCESS(_("Purged {n} orphan(s).").format(n=report["purged"]))
            )
        if not report["orphaned"]:
            self.stdout.write(self.style.SUCCESS(_("No orphans found.")))
