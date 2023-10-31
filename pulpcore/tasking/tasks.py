import asyncio
import contextlib
import contextvars
import importlib
import logging
import sys
import traceback
from gettext import gettext as _

from django.db import connection, transaction
from django.db.models import Model
from django_guid import get_guid
from pulpcore.app.apps import MODULE_PLUGIN_VERSIONS
from pulpcore.app.loggers import deprecation_logger
from pulpcore.app.models import Task
from pulpcore.app.util import current_task, get_domain, get_url
from pulpcore.constants import TASK_FINAL_STATES, TASK_INCOMPLETE_STATES, TASK_STATES

_logger = logging.getLogger(__name__)


def _validate_and_get_resources(resources):
    resource_set = set()
    for r in resources:
        if isinstance(r, str):
            resource_set.add(r)
        elif isinstance(r, Model):
            resource_set.add(get_url(r))
        elif r is None:
            # Silently drop None values
            pass
        else:
            raise ValueError(_("Must be (str|Model)"))
    return list(resource_set)


def wakeup_worker():
    # Notify workers
    with connection.connection.cursor() as cursor:
        cursor.execute("NOTIFY pulp_worker_wakeup")


def execute_task(task):
    # This extra stack is needed to isolate the current_task ContextVar
    contextvars.copy_context().run(_execute_task, task)


def _execute_task(task):
    # Store the task id in the context for `Task.current()`.
    current_task.set(task)
    task.set_running()
    try:
        _logger.info(_("Starting task %s"), task.pk)

        # Execute task
        module_name, function_name = task.name.rsplit(".", 1)
        module = importlib.import_module(module_name)
        func = getattr(module, function_name)
        args = task.enc_args or ()
        kwargs = task.enc_kwargs or {}
        result = func(*args, **kwargs)
        if asyncio.iscoroutine(result):
            _logger.debug(_("Task is coroutine %s"), task.pk)
            loop = asyncio.get_event_loop()
            loop.run_until_complete(result)

    except Exception:
        exc_type, exc, tb = sys.exc_info()
        task.set_failed(exc, tb)
        _logger.info(_("Task %s failed (%s)"), task.pk, exc)
        _logger.info("\n".join(traceback.format_list(traceback.extract_tb(tb))))
    else:
        task.set_completed()
        _logger.info(_("Task completed %s"), task.pk)


def dispatch(
    func,
    args=None,
    kwargs=None,
    task_group=None,
    exclusive_resources=None,
    shared_resources=None,
    immediate=False,
    deferred=True,
    versions=None,
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
        immediate (bool): Whether to allow running this task immediately. It must be guaranteed to
            execute fast without blocking. If not all resource constraints are met, the task will
            either be returned in a canceled state or, if `deferred` is `True` be left in the queue
            to be picked up by a worker eventually. Defaults to `False`.
        deferred (bool): Whether to allow defer running the task to a pulpcore_worker. Defaults to
            `True`. `immediate` and `deferred` cannot both be `False`.
        versions (Optional[Dict[str, str]]): Minimum versions of components by app_label the worker
            must provide to handle the task.

    Returns (pulpcore.app.models.Task): The Pulp Task that was created.

    Raises:
        ValueError: When `resources` is an unsupported type.
    """

    assert deferred or immediate, "A task must be at least `deferred` or `immediate`."

    if callable(func):
        function_name = f"{func.__module__}.{func.__name__}"
    else:
        function_name = func

    if versions is None:
        try:
            versions = MODULE_PLUGIN_VERSIONS[function_name.split(".", maxsplit=1)[0]]
        except KeyError:
            deprecation_logger.warn(
                _(
                    "Using functions outside of pulp components as tasks is not supported and will "
                    "result in runtime errors with pulpcore>=3.40."
                )
            )
            # The best we can do now...
            versions = MODULE_PLUGIN_VERSIONS["pulpcore"]

    if exclusive_resources is None:
        exclusive_resources = []
    else:
        exclusive_resources = _validate_and_get_resources(exclusive_resources)
    if shared_resources is None:
        shared_resources = []
    else:
        shared_resources = _validate_and_get_resources(shared_resources)

    # A task that is exclusive on a domain will block all tasks within that domain
    domain_url = get_url(get_domain())
    if domain_url not in exclusive_resources:
        shared_resources.append(domain_url)
    resources = exclusive_resources + [f"shared:{resource}" for resource in shared_resources]

    notify_workers = False
    with contextlib.ExitStack() as stack:
        with transaction.atomic():
            task = Task.objects.create(
                state=TASK_STATES.WAITING,
                logging_cid=(get_guid()),
                task_group=task_group,
                name=function_name,
                enc_args=args,
                enc_kwargs=kwargs,
                parent_task=Task.current(),
                reserved_resources_record=resources,
                versions=versions,
            )
            if immediate:
                # Grab the advisory lock before the task hits the db.
                stack.enter_context(task)
            else:
                notify_workers = True
        if immediate:
            prior_tasks = Task.objects.filter(
                state__in=TASK_INCOMPLETE_STATES, pulp_created__lt=task.pulp_created
            )
            # Compile a list of resources that must not be taken by other tasks.
            colliding_resources = (
                shared_resources
                + exclusive_resources
                + [f"shared:{resource}" for resource in exclusive_resources]
            )
            # Can we execute this task immediately?
            if (
                not colliding_resources
                or not prior_tasks.filter(
                    reserved_resources_record__overlap=colliding_resources
                ).exists()
            ):
                execute_task(task)
                if resources:
                    notify_workers = True
            elif deferred:
                notify_workers = True
            else:
                task.set_canceling()
                task.set_canceled(TASK_STATES.CANCELED, "Resources temporarily unavailable.")
    if notify_workers:
        wakeup_worker()
    return task


def cancel_task(task_id):
    """
    Cancel the task that is represented by the given task_id.

    This method cancels only the task with given task_id, not the spawned tasks. This also updates
    task's state to 'canceling'.

    Args:
        task_id (str): The ID of the task you wish to cancel

    Raises:
        rest_framework.exceptions.NotFound: If a task with given task_id does not exist
    """
    task = Task.objects.get(pk=task_id)

    if task.state in TASK_FINAL_STATES:
        # If the task is already done, just stop
        _logger.debug(
            "Task [{task_id}] already in a final state: {state}".format(
                task_id=task_id, state=task.state
            )
        )
        return task

    _logger.info(_("Canceling task: {id}").format(id=task_id))

    # This is the only valid transition without holding the task lock
    task.set_canceling()
    # Notify the worker that might be running that task and other workers to clean up
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_notify('pulp_worker_cancel', %s)", (str(task.pk),))
        cursor.execute("NOTIFY pulp_worker_wakeup")
    return task
