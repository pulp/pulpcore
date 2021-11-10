from gettext import gettext as _
from django_currentuser.middleware import get_current_authenticated_user
from pulpcore.app.models import (
    ProgressReport,
    Task,
)
from pulpcore.app.role_util import get_objects_for_user


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
    qs = Task.objects.filter(finished_at__lt=finished_before, state__in=states)
    units_deleted, details = get_objects_for_user(current_user, "core.delete_task", qs=qs).delete()

    # Progress bar reporting total-units
    progress_bar = ProgressReport(
        message=_("Purged task-objects total"),
        total=units_deleted,
        code="purge.tasks.total",
        done=units_deleted,
        state="completed",
    )
    progress_bar.save()
    # This loop reports back the specific entities deleted and the number removed
    for key in details:
        progress_bar = ProgressReport(
            message=_("Purged task-objects of type {}".format(key)),
            total=details[key],
            code="purge.tasks.key.{}".format(key),
            done=details[key],
            state="completed",
        )
        progress_bar.save()
