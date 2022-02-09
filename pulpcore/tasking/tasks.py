import logging
from gettext import gettext as _

from django.db import transaction, connection
from django.db.models import Model, Q
from django.utils import timezone
from django_guid import get_guid

from pulpcore.app.models import Task, TaskSchedule
from pulpcore.constants import TASK_FINAL_STATES, TASK_STATES
from pulpcore.tasking import util

_logger = logging.getLogger(__name__)


TASK_TIMEOUT = -1  # -1 for infinite timeout


def _validate_and_get_resources(resources):
    resource_set = set()
    for r in resources:
        if isinstance(r, str):
            resource_set.add(r)
        elif isinstance(r, Model):
            resource_set.add(util.get_url(r))
        else:
            raise ValueError(_("Must be (str|Model)"))
    return list(resource_set)


def _wakeup_worker():
    # Notify workers
    with connection.connection.cursor() as cursor:
        cursor.execute("NOTIFY pulp_worker_wakeup")


def dispatch(
    func,
    args=None,
    kwargs=None,
    task_group=None,
    exclusive_resources=None,
    shared_resources=None,
):
    """
    Enqueue a message to Pulp workers with a reservation.

    This method provides normal enqueue functionality, while also requesting necessary locks for
    serialized urls. No two tasks that claim the same resource can execute concurrently. It
    accepts resources which it transforms into a list of urls (one for each resource).

    This method creates a :class:`pulpcore.app.models.Task` object and returns it.

    The values in `args` and `kwargs` must be JSON serializable, but may contain instances of
    ``uuid.UUID``.

    Args:
        func (callable | str): The function to be run when the necessary locks are acquired.
        args (tuple): The positional arguments to pass on to the task.
        kwargs (dict): The keyword arguments to pass on to the task.
        task_group (pulpcore.app.models.TaskGroup): A TaskGroup to add the created Task to.
        exclusive_resources (list): A list of resources this task needs exclusive access to while
            running. Each resource can be either a `str` or a `django.models.Model` instance.
        shared_resources (list): A list of resources this task needs non-exclusive access to while
            running. Each resource can be either a `str` or a `django.models.Model` instance.

    Returns (pulpcore.app.models.Task): The Pulp Task that was created.

    Raises:
        ValueError: When `resources` is an unsupported type.
    """

    if callable(func):
        func = f"{func.__module__}.{func.__name__}"

    if exclusive_resources is None:
        exclusive_resources = []

    resources = _validate_and_get_resources(exclusive_resources)
    if shared_resources:
        resources.extend(
            (f"shared:{resource}" for resource in _validate_and_get_resources(shared_resources))
        )
    with transaction.atomic():
        task = Task.objects.create(
            state=TASK_STATES.WAITING,
            logging_cid=(get_guid() or ""),
            task_group=task_group,
            name=func,
            args=args,
            kwargs=kwargs,
            parent_task=Task.current(),
            reserved_resources_record=resources,
        )
        transaction.on_commit(_wakeup_worker)

    return task


def dispatch_scheduled_tasks():
    # Warning, dispatch_scheduled_tasks is not race condition free!
    now = timezone.now()
    # Dispatch all tasks old enough and not still running
    for task_schedule in TaskSchedule.objects.filter(next_dispatch__lte=now).filter(
        Q(last_task=None) | Q(last_task__state__in=TASK_FINAL_STATES)
    ):
        try:
            if task_schedule.dispatch_interval is None:
                # This was a timed one shot task schedule
                task_schedule.next_dispatch = None
            else:
                # This is a recurring task schedule
                while task_schedule.next_dispatch < now:
                    # Do not schedule in the past
                    task_schedule.next_dispatch += task_schedule.dispatch_interval
            with transaction.atomic():
                task_schedule.last_task = dispatch(
                    task_schedule.task_name,
                )
                task_schedule.save(update_fields=["next_dispatch", "last_task"])

            _logger.info(
                _("Dispatched scheduled task {task_name} as task id {task_id}").format(
                    task_name=task_schedule.task_name, task_id=task_schedule.last_task.pk
                )
            )
        except Exception as e:
            _logger.warn(
                _("Dispatching scheduled task {task_name} failed. {error}").format(
                    task_name=task_schedule.task_name, error=str(e)
                )
            )
