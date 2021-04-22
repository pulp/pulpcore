import logging
import time
from hashlib import blake2s
from gettext import gettext as _

from django.conf import settings
from django.db import transaction
from django.db import connection as db_connection
from django.urls import reverse
from rq.command import send_stop_job_command
from rq.exceptions import InvalidJobOperation, NoSuchJobError
from rq.job import Job, get_current_job
from rq.worker import Worker

from pulpcore.app.models import Task
from pulpcore.app.util import get_view_name_for_model
from pulpcore.constants import TASK_FINAL_STATES, TASK_INCOMPLETE_STATES, TASK_STATES
from pulpcore.exceptions import MissingResource
from pulpcore.tasking import connection

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

    if settings.USE_NEW_WORKER_TYPE:
        task = task_status
        # This is the only valid transition without holding the task lock
        rows = Task.objects.filter(pk=task.pk, state__in=TASK_INCOMPLETE_STATES).update(
            state=TASK_STATES.CANCELING
        )
        # Notify the worker that might be running that task and other workers to clean up
        with db_connection.cursor() as cursor:
            cursor.execute("SELECT pg_notify('pulp_worker_cancel', %s)", (str(task.pk),))
            cursor.execute("NOTIFY pulp_worker_wakeup")
        if rows == 1:
            task.refresh_from_db()
        return task

    redis_conn = connection.get_redis_connection()
    job = Job(id=str(task_status.pk), connection=redis_conn)
    resource_job = Job(id=str(task_status._resource_job_id), connection=redis_conn)

    task_status.state = TASK_STATES.CANCELED
    task_status.save()

    resource_job.cancel()
    job.cancel()

    try:
        send_stop_job_command(redis_conn, job.get_id())
        send_stop_job_command(redis_conn, resource_job.get_id())
    except (InvalidJobOperation, NoSuchJobError):
        # We don't care if the job isn't currently running when we try to cancel
        pass

    # A hack to ensure that we aren't deleting resources still being used by the workhorse
    time.sleep(0.5)

    with transaction.atomic():
        for report in task_status.progress_reports.all():
            if report.state not in TASK_FINAL_STATES:
                report.state = TASK_STATES.CANCELED
                report.save()
        _delete_incomplete_resources(task_status)
        task_status.release_resources()

    return task_status


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


def get_current_worker():
    """
    Get the rq worker assigned to the current job

    Returns:
       class:`rq.worker.Worker`: The worker assigned to the current job
    """
    for worker in Worker.all():
        if worker.get_current_job() == get_current_job():
            return worker

    return None


def _hash_to_u64(value):
    _digest = blake2s(value.encode(), digest_size=8).digest()
    return int.from_bytes(_digest, byteorder="big", signed=True)
