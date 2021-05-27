import logging
from gettext import gettext as _

from pulpcore.app.models import Worker, Task
from pulpcore.app.settings import WORKER_TTL
from pulpcore.constants import TASK_INCOMPLETE_STATES
from pulpcore.tasking import connection
from pulpcore.tasking.constants import TASKING_CONSTANTS
from pulpcore.tasking.util import cancel

from rq.exceptions import NoSuchJobError
from rq.job import Job

from django.db import transaction


_logger = logging.getLogger(__name__)


def handle_worker_heartbeat(worker_name):
    """
    This is a generic function for updating worker heartbeat records.

    Existing Worker objects are searched for one to update. If an existing one is found, it is
    updated. Otherwise a new Worker entry is created. Logging at the info level is also done.

    Args:
        worker_name (str): The hostname of the worker
    """
    worker, created = Worker.objects.get_or_create(name=worker_name)

    if created:
        _logger.info(_("New worker '{name}' discovered").format(name=worker_name))
    elif worker.online is False:
        worker.gracefully_stopped = False
        worker.cleaned_up = False
        worker.save()
        _logger.info(_("Worker '{name}' is back online.").format(name=worker_name))

    worker.save_heartbeat()

    msg = _("Worker heartbeat from '{name}' at time {timestamp}").format(
        timestamp=worker.last_heartbeat, name=worker_name
    )

    _logger.debug(msg)

    return worker


def check_worker_processes():
    """
    Look for missing Pulp worker processes, log and cleanup as needed.

    To find a missing Worker process, filter the Workers model for entries older than
    utcnow() - WORKER_TTL. The heartbeat times are stored in native UTC, so this is
    a comparable datetime. For each missing worker found, call mark_worker_offline()
    synchronously for cleanup.

    This method also checks that at least one resource-manager and one worker process is
    present. If there are zero of either, log at the error level that Pulp will not operate
    correctly.
    """
    msg = (
        _(
            "Checking if pulpcore-workers or pulpcore-resource-manager processes are "
            "missing for more than %d seconds"
        )
        % WORKER_TTL
    )
    _logger.debug(msg)

    for worker in Worker.objects.dirty_workers():
        msg = _("Worker '%s' has gone missing, removing from list of workers") % worker.name
        _logger.error(msg)

        mark_worker_offline(worker.name)

    worker_count = (
        Worker.objects.online_workers()
        .exclude(name=TASKING_CONSTANTS.RESOURCE_MANAGER_WORKER_NAME)
        .count()
    )

    resource_manager_count = (
        Worker.objects.online_workers()
        .filter(name=TASKING_CONSTANTS.RESOURCE_MANAGER_WORKER_NAME)
        .count()
    )

    if resource_manager_count == 0:
        msg = _(
            "There are 0 pulpcore-resource-manager processes running. Pulp will not operate "
            "correctly without at least one pulpcore-resource-manager process running."
        )
        _logger.error(msg)

    if worker_count == 0:
        msg = _(
            "There are 0 task worker processes running. Pulp will not operate "
            "correctly without at least one task worker process running."
        )
        _logger.error(msg)

    output_dict = {"workers": worker_count, "resource-manager": resource_manager_count}
    msg = (
        _(
            "%(workers)d pulpcore-worker processes and %(resource-manager)d "
            "pulpcore-resource-manager processes"
        )
        % output_dict
    )
    _logger.debug(msg)


def check_and_cancel_missing_tasks():
    """Cancel any unexecuted Tasks which are no longer in the RQ registry.

    In some situations such as a restart of Redis, Jobs can be dropped from the Redis
    queues and "forgotten". Therefore the Task will never be marked completed in Pulp
    and are never cleaned up. This results in stray resource locks that cause workers
    to deadlock.

    We go through all of the tasks which are in an incomplete state and check that RQ
    still has a record of the job. If not, we cancel it.
    """
    redis_conn = connection.get_redis_connection()

    assigned_and_unfinished_tasks = Task.objects.filter(
        state__in=TASK_INCOMPLETE_STATES, worker__in=Worker.objects.online_workers()
    )

    for task in assigned_and_unfinished_tasks:
        try:
            Job.fetch(str(task.pk), connection=redis_conn)
        except NoSuchJobError:
            cancel(task.pk)

    # Also go through all of the tasks that were still queued up on the resource manager
    for task in Task.objects.filter(worker__isnull=True):
        try:
            Job.fetch(str(task._resource_job_id), connection=redis_conn)
        except NoSuchJobError:
            cancel(task.pk)


def mark_worker_offline(worker_name, normal_shutdown=False):
    """
    Mark the :class:`~pulpcore.app.models.Worker` as offline and cancel associated tasks.

    If the worker shutdown normally, no message is logged, otherwise an error level message is
    logged. Default is to assume the worker did not shut down normally.

    Any resource reservations associated with this worker are cleaned up by this function.

    Any tasks associated with this worker are explicitly canceled.

    Args:
        worker_name (str) The name of the worker
        normal_shutdown (bool): True if the worker shutdown normally, False otherwise. Defaults to
                                False.
    """
    if not normal_shutdown:
        msg = _("The worker named %(name)s is missing. Canceling the tasks in its queue.")
        _logger.error(msg % {"name": worker_name})
    else:
        _logger.info(_("Worker '{name}' shutdown".format(name=worker_name)))
        _logger.info(_("Cleaning up shutdown worker '{name}'.".format(name=worker_name)))

    try:
        with transaction.atomic():
            worker = Worker.objects.select_for_update().get(
                name=worker_name, gracefully_stopped=False, cleaned_up=False
            )
            # Cancel all of the tasks that were assigned to this worker's queue
            for task in worker.tasks.filter(state__in=TASK_INCOMPLETE_STATES):
                cancel(task.pk)

            # Ensure all locks are released for those tasks that are in final states also
            for task in worker.tasks.exclude(state__in=TASK_INCOMPLETE_STATES):
                task.release_resources()

            if normal_shutdown:
                worker.gracefully_stopped = True

            worker.cleaned_up = True
            worker.save()
    except Worker.DoesNotExist:
        pass
