import logging
from gettext import gettext as _

from django.db import transaction
from django.db import connection
from django.urls import reverse

from pulpcore.app.models import Task
from pulpcore.app.util import get_view_name_for_model
from pulpcore.constants import TASK_FINAL_STATES, TASK_INCOMPLETE_STATES, TASK_STATES
from pulpcore.exceptions import MissingResource

_logger = logging.getLogger(__name__)


def cancel(task_id):
    """
    Cancel the task that is represented by the given task_id.

    This method cancels only the task with given task_id, not the spawned tasks. This also updates
    task's state to either 'canceled' or 'canceling'.

    Args:
        task_id (str): The ID of the task you wish to cancel

    Raises:
        MissingResource: if a task with given task_id does not exist
    """
    try:
        task_status = Task.objects.get(pk=task_id)
    except Task.DoesNotExist:
        raise MissingResource(task=task_id)

    if task_status.state in TASK_FINAL_STATES:
        # If the task is already done, just stop
        msg = _("Task [{task_id}] already in a final state: {state}")
        _logger.debug(msg.format(task_id=task_id, state=task_status.state))
        return task_status

    _logger.info(_("Canceling task: {id}").format(id=task_id))

    task = task_status
    # This is the only valid transition without holding the task lock
    rows = Task.objects.filter(pk=task.pk, state__in=TASK_INCOMPLETE_STATES).update(
        state=TASK_STATES.CANCELING
    )
    # Notify the worker that might be running that task and other workers to clean up
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_notify('pulp_worker_cancel', %s)", (str(task.pk),))
        cursor.execute("NOTIFY pulp_worker_wakeup")
    if rows == 1:
        task.refresh_from_db()
    return task


def _delete_incomplete_resources(task):
    """
    Delete all incomplete created-resources on a canceled task.

    Args:
        task (Task): A task.
    """
    if task.state not in [TASK_STATES.CANCELED, TASK_STATES.CANCELING]:
        raise RuntimeError(_("Task must be canceled."))
    for model in (r.content_object for r in task.created_resources.all()):
        try:
            if model.complete:
                continue
        except AttributeError:
            continue
        try:
            with transaction.atomic():
                model.delete()
        except Exception as error:
            _logger.error(_("Delete created resource, failed: {}").format(str(error)))


def get_url(model):
    """
    Get a resource url for the specified model object. This returns the path component of the
    resource URI.  This is used in our resource locking/reservation code to identify resources.

    Args:
        model (django.models.Model): A model object.

    Returns:
        str: The path component of the resource url
    """
    return reverse(get_view_name_for_model(model, "detail"), args=[model.pk])
