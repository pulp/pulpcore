from gettext import gettext as _

from django.core.management import BaseCommand
from django.db.models import F

from pulpcore.app.models import ProgressReport
from pulpcore.constants import TASK_STATES


class Command(BaseCommand):
    """Django management command for repairing progress-reports in inconsistent states."""

    help = (
        "Repairs issue #3609. Long-running tasks that utilize ProgressReports, which "
        "fail or are cancelled, can leave their associated reports in state 'running'. "
        "This script finds the ProgressReports marked as 'running', whose owning task "
        "is in either 'cancelled or 'failed', and moves the state of the ProgressReport "
        "to match that of the task."
    )

    def add_arguments(self, parser):
        """Set up arguments."""
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help=_(
                "Don't modify anything, just collect results on how many ProgressReports "
                "are impacted."
            ),
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        for state in [TASK_STATES.CANCELED, TASK_STATES.FAILED]:
            if dry_run:
                to_be_updated = ProgressReport.objects.filter(
                    task__state__ne=F("state"), state=TASK_STATES.RUNNING, task__state=state
                ).count()
                print(
                    _("Number of ProgressReports in inconsistent state for {} tasks: {}").format(
                        state, to_be_updated
                    )
                )
            else:
                updated = ProgressReport.objects.filter(
                    task__state__ne=F("state"), state=TASK_STATES.RUNNING, task__state=state
                ).update(state=state)
                print(
                    _("Number of ProgressReports updated for {} tasks: {}").format(state, updated)
                )
