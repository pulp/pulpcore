from gettext import gettext as _
from logging import getLogger

from django.conf import settings
from django.db.models.deletion import ProtectedError
from django.utils import timezone
from django.contrib.auth import get_user_model

from pulpcore.app.models import (
    ProgressReport,
    Task,
)
from pulpcore.app.role_util import get_objects_for_user
from pulpcore.app.util import current_task, get_domain, get_current_authenticated_user
from pulpcore.constants import TASK_STATES, TASK_FINAL_STATES

log = getLogger(__name__)

User = get_user_model()

# Delete 1K at a time - better to use less memory, and take a little longer, with a utility
# function like this.
DELETE_LIMIT = 1000
# Key that delete() returns for Tasks
TASK_KEY = "core.Task"


def _details_reporting(current_reports, current_details, totals_pb):
    """Create and update progress-reports for each detail-key returned from a delete() call.

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


# Versions of this task up until at least 3.74 may not know about the user_pk argument.
# We need to handle them accordingly.
def purge(finished_before=None, states=None, **kwargs):
    """This task purges from the database records of tasks which finished prior to the specified
    time.

    It will remove only tasks that are 'deletable' by the current-user (admin-users own All The
    Things, so admins can delete all tasks). It will only delete tasks within the domain this task
    was triggered in.
    If scheduled, deletion is not limited to a user.

    It will not remove tasks that are incomplete (ie, in states running|waiting|cancelling).

    It reports (using ProgressReport) the total entities deleted, as well as individual counts
    for each class of entity. This shows the results of cascading-deletes that are triggered
    by deleting a Task.

    Args:
        finished_before (Optional[DateTime]): Earliest finished-time to **NOT** purge.
        states (Optional[List[str]]): List of task-states we want to purge.
    """
    if finished_before is None:
        assert settings.TASK_PROTECTION_TIME > 0
        finished_before = timezone.now() - timezone.timedelta(minutes=settings.TASK_PROTECTION_TIME)
    if states is None:
        states = TASK_FINAL_STATES
    domain = get_domain()
    # Tasks, prior to the specified date, in the specified state, owned by the current-user, in the
    # current domain
    candidate_qs = Task.objects.filter(
        finished_at__lt=finished_before, state__in=states, pulp_domain=domain
    )
    if "user_pk" in kwargs:
        if (user_pk := kwargs["user_pk"]) is not None:
            current_user = User.objects.get(pk=user_pk)
            candidate_qs = get_objects_for_user(current_user, "core.delete_task", qs=candidate_qs)
    else:
        # This is the old task signature (<= 3.74) without "user_pk".
        # Has this task not been dispatched from a task schedule? Then we assume there was a user
        # doing that.
        if not current_task.get().taskschedule_set.exists():
            current_user = get_current_authenticated_user()
            if current_user is None:
                raise RuntimeError(
                    "This task should have been dispatched by a user. Cannot find it though. "
                    "Maybe it got deleted."
                )
            candidate_qs = get_objects_for_user(current_user, "core.delete_task", qs=candidate_qs)
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

    # Build and save a progress-report for objects that couldn't be deleted
    error_pb = ProgressReport(
        message=_("Tasks failed to purge"),
        total=None,
        code="purge.tasks.error",
        done=0,
    )
    error_pb.save()
    # Also keep a list of PKs of objects we've already failed to delete
    pks_failed = []

    # Our delete-query is going to deal with "the first DELETE_LIMIT tasks that match our
    # criteria", looping until we've deleted everything that fits our parameters
    continue_deleting = True

    while continue_deleting:
        # Get a list of candidate objects to delete
        candidate_pks = candidate_qs.exclude(pk__in=pks_failed).values_list("pk", flat=True)
        pk_list = list(candidate_pks[:DELETE_LIMIT])

        # Try deleting the objects in bulk
        try:
            units_deleted, details = Task.objects.filter(pk__in=pk_list).delete()
            _details_reporting(details_reports, details, totals_pb)
            continue_deleting = units_deleted > 0
        except ProtectedError:
            # If there was at least one object that couldn't be deleted, then
            # loop through the candidate objects and delete them one-by-one
            for pk in pk_list:
                try:
                    obj = Task.objects.get(pk=pk)
                    count, details = obj.delete()
                    _details_reporting(details_reports, details, totals_pb)
                except ProtectedError as e:
                    # Object could not be deleted due to foreign key constraint.
                    # Log the details of the object.
                    error_pb.done += 1
                    pks_failed.append(pk)
                    log.debug(e)

    # Complete the progress-reports for the specific entities deleted
    for key, pb in details_reports.items():
        pb.total = pb.done
        pb.state = TASK_STATES.COMPLETED
        pb.save()

    # Complete the totals-ProgressReport
    totals_pb.total = totals_pb.done
    totals_pb.state = TASK_STATES.COMPLETED
    totals_pb.save()

    # Complete the error-ProgressReport
    error_pb.total = error_pb.done
    error_pb.state = TASK_STATES.COMPLETED
    error_pb.save()
