from gettext import gettext as _

from django_currentuser.middleware import get_current_authenticated_user
from pulpcore.app.models import (
    ProgressReport,
    Task,
)
from pulpcore.app.role_util import get_objects_for_user
from pulpcore.constants import TASK_STATES

# Delete 1K at a time - better to use less memory, and take a little longer, with a utility
# function like this.
DELETE_LIMIT = 1000
# Key that delete() returns for Tasks
TASK_KEY = "core.Task"


def _details_reporting(current_reports, current_details, totals_pb):
    """
    Create and update progress-reports for each detail-key returned from a delete() call.

    We don't know how many entities will be deleted via cascade-delete until we're all done.

    The function has one special case: we know how many Tasks we're expecting to delete right
    from the beginning. Therefore, we "assume" that the key `core.Task` has been pre-seeded
    with a ProgressReport whose total is correct, in advance, and therefore don't update
    total for that key.

    Args:
        current_reports (dict): key:ProgressReport to record into
    Returns:
        updated current_reports
    """
    entity_count = 0
    for key, curr_detail in current_details.items():
        entity_count += current_details[key]
        if key in current_reports:
            current_reports[key].increase_by(curr_detail)
        else:
            pb = ProgressReport(
                message=_("Purged task-objects of type {}".format(key)),
                code="purge.tasks.key.{}".format(key),
                total=None,
                done=curr_detail,
            )
            pb.save()
            current_reports[key] = pb
    # Update/save totals once
    totals_pb.increase_by(entity_count)
    return current_reports


def purge(finished_before, states):
    """
    This task purges from the database records of tasks which finished prior to the specified time.

    It will remove only tasks that are 'owned' by the current-user (admin-users own All The Things,
    so admins can delete all tasks).

    It will not remove tasks that are incomplete (ie, in states running|waiting|cancelling).

    It reports (using ProgressReport) the total entities deleted, as well as individual counts
    for each class of entity. This shows the results of cascading-deletes that are triggered
    by deleting a Task.

    Args:
        finished_before (DateTime): Earliest finished-time to **NOT** purge.
        states (List[str]): List of task-states we want to purge.

    """
    current_user = get_current_authenticated_user()
    # Tasks, prior to the specified date, in the specified state, owned by the current-user
    tasks_qs = Task.objects.filter(finished_at__lt=finished_before, state__in=states)
    candidate_qs = get_objects_for_user(current_user, "core.delete_task", qs=tasks_qs)
    # Progress bar reporting total-units
    totals_pb = ProgressReport(
        message=_("Purged task-related-objects total"),
        total=None,
        code="purge.tasks.total",
        done=0,
    )
    totals_pb.save()
    # Dictionary to hold progress-reports by delete-details-key
    details_reports = {}

    # Figure out how many Tasks owned by the current user we're about to delete
    expected_total = candidate_qs.count()
    # Build and save a progress-report for that detail
    pb = ProgressReport(
        message=_("Purged task-objects of type {}".format(TASK_KEY)),
        total=expected_total,
        code="purge.tasks.key.{}".format(TASK_KEY),
        done=0,
    )
    pb.save()
    details_reports[TASK_KEY] = pb

    # Our delete-query is going to deal with "the first DELETE_LIMIT tasks that match our
    # criteria", looping until we've deleted everything that fits our parameters
    units_deleted = 1
    # Until our query returns "No tasks deleted", add results into totals and Do It Again
    while units_deleted > 0:
        units_deleted, details = Task.objects.filter(
            pk__in=candidate_qs[:DELETE_LIMIT].values_list("pk", flat=True)
        ).delete()
        _details_reporting(details_reports, details, totals_pb)

    # Complete the progress-reports for the specific entities deleted
    for key, pb in details_reports.items():
        pb.total = pb.done
        pb.state = TASK_STATES.COMPLETED
        pb.save()

    # Complete the totals-ProgressReport
    totals_pb.total = totals_pb.done
    totals_pb.state = TASK_STATES.COMPLETED
    totals_pb.save()
