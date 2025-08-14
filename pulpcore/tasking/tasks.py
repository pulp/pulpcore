import asyncio
import contextlib
import contextvars
import importlib
import logging
import os
import sys
import traceback
import tempfile
import threading
from gettext import gettext as _

from django.conf import settings
from django.db import connection, transaction
from django.db.models import Model
from django_guid import get_guid
from pulpcore.app.apps import MODULE_PLUGIN_VERSIONS
from pulpcore.app.models import Task, TaskGroup, AppStatus
from pulpcore.app.util import (
    current_task,
    get_domain,
    get_prn,
)
from pulpcore.constants import (
    TASK_FINAL_STATES,
    TASK_INCOMPLETE_STATES,
    TASK_STATES,
    IMMEDIATE_TIMEOUT,
    TASK_WAKEUP_UNBLOCK,
)
from pulpcore.middleware import x_task_diagnostics_var
from pulpcore.tasking.kafka import send_task_notification

_logger = logging.getLogger(__name__)


def _validate_and_get_resources(resources):
    resource_set = set()
    for r in resources:
        if isinstance(r, str):
            resource_set.add(r)
        elif isinstance(r, Model):
            resource_set.add(get_prn(r))
        elif r is None:
            # Silently drop None values
            pass
        else:
            raise ValueError(_("Must be (str|Model)"))
    return list(resource_set)


def wakeup_worker(reason="unknown"):
    # Notify workers
    with connection.connection.cursor() as cursor:
        cursor.execute("SELECT pg_notify('pulp_worker_wakeup', %s)", (reason,))


def execute_task(task):
    # This extra stack is needed to isolate the current_task ContextVar
    contextvars.copy_context().run(_execute_task, task)


def _execute_task(task):
    # Store the task id in the context for `Task.current()`.
    current_task.set(task)
    task.set_running()
    domain = get_domain()
    try:
        _logger.info(
            "Starting task id: %s in domain: %s, task_type: %s, immediate: %s, deferred: %s",
            task.pk,
            domain.name,
            task.name,
            str(task.immediate),
            str(task.deferred),
        )

        # Execute task
        module_name, function_name = task.name.rsplit(".", 1)
        module = importlib.import_module(module_name)
        func = getattr(module, function_name)
        args = task.enc_args or ()
        kwargs = task.enc_kwargs or {}
        immediate = task.immediate
        is_coroutine_fn = asyncio.iscoroutinefunction(func)

        if immediate and not is_coroutine_fn:
            raise ValueError("Immediate tasks must be async functions.")

        if is_coroutine_fn:
            # both regular and immediate tasks can be coroutines, but only immediate must timeout
            _logger.debug("Task is coroutine %s", task.pk)
            coro = func(*args, **kwargs)
            if immediate:
                coro = asyncio.wait_for(coro, timeout=IMMEDIATE_TIMEOUT)
            loop = asyncio.get_event_loop()
            try:
                loop.run_until_complete(coro)
            except asyncio.TimeoutError:
                _logger.info(
                    "Immediate task %s timed out after %s seconds.", task.pk, IMMEDIATE_TIMEOUT
                )
                raise RuntimeError(
                    "Immediate task timed out after {timeout} seconds.".format(
                        timeout=IMMEDIATE_TIMEOUT,
                    )
                )
        else:
            func(*args, **kwargs)

    except Exception:
        exc_type, exc, tb = sys.exc_info()
        task.set_failed(exc, tb)
        _logger.info(
            "Task[{task_type}] {task_pk} failed ({exc_type}: {exc}) in domain: {domain}".format(
                task_type=task.name,
                task_pk=task.pk,
                exc_type=exc_type.__name__,
                exc=exc,
                domain=domain.name,
            )
        )
        _logger.info("\n".join(traceback.format_list(traceback.extract_tb(tb))))
        send_task_notification(task)
    else:
        task.set_completed()
        execution_time = task.finished_at - task.started_at
        execution_time_us = int(execution_time.total_seconds() * 1_000_000)  # μs
        _logger.info(
            "Task completed %s in domain:"
            " %s, task_type: %s, immediate: %s, deferred: %s, execution_time: %s μs",
            task.pk,
            domain.name,
            task.name,
            str(task.immediate),
            str(task.deferred),
            execution_time_us,
        )
        send_task_notification(task)


def running_from_thread_pool() -> bool:
    # TODO: this needs an alternative approach ASAP!
    # Currently we rely on the weak fact that ThreadPoolExecutor names threads like:
    # "ThreadPoolExecutor-0_0"
    thread_name = threading.current_thread().name
    return "ThreadPoolExecutor" in thread_name


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

    This method creates a [pulpcore.app.models.Task][] object and returns it.

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

    # Can't run short tasks immediately if running from thread pool
    immediate = immediate and not running_from_thread_pool()
    assert deferred or immediate, "A task must be at least `deferred` or `immediate`."

    if callable(func):
        function_name = f"{func.__module__}.{func.__name__}"
    else:
        function_name = func

    if versions is None:
        versions = MODULE_PLUGIN_VERSIONS[function_name.split(".", maxsplit=1)[0]]

    if exclusive_resources is None:
        exclusive_resources = []
    else:
        exclusive_resources = _validate_and_get_resources(exclusive_resources)
    if shared_resources is None:
        shared_resources = []
    else:
        shared_resources = _validate_and_get_resources(shared_resources)

    # A task that is exclusive on a domain will block all tasks within that domain
    domain_prn = get_prn(get_domain())
    if domain_prn not in exclusive_resources:
        shared_resources.append(domain_prn)
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
                immediate=immediate,
                deferred=deferred,
                profile_options=x_task_diagnostics_var.get(None),
                app_lock=(immediate and AppStatus.objects.current()) or None,
            )
            task.refresh_from_db()  # The database may have assigned a timestamp for us.
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
                task.unblock()

                cur_dir = os.getcwd()
                with tempfile.TemporaryDirectory(dir=settings.WORKING_DIRECTORY) as working_dir:
                    os.chdir(working_dir)
                    try:
                        execute_task(task)
                    finally:
                        # Whether the task fails or not, we should always restore the workdir.
                        os.chdir(cur_dir)

                if resources:
                    notify_workers = True
            elif deferred:
                # Resources are blocked. Let the others handle it.
                notify_workers = True
                task.app_lock = None
                task.save()
            else:
                task.set_canceling()
                task.set_canceled(TASK_STATES.CANCELED, "Resources temporarily unavailable.")
    if notify_workers:
        wakeup_worker(TASK_WAKEUP_UNBLOCK)
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
    task = Task.objects.select_related("pulp_domain").get(pk=task_id)

    if task.state in TASK_FINAL_STATES:
        # If the task is already done, just stop
        _logger.debug(
            "Task [{task_id}] in domain: {name} already in a final state: {state}".format(
                task_id=task_id, name=task.pulp_domain.name, state=task.state
            )
        )
        return task
    _logger.info(
        "Canceling task: {id} in domain: {name}".format(id=task_id, name=task.pulp_domain.name)
    )

    # This is the only valid transition without holding the task lock
    task.set_canceling()
    # Notify the worker that might be running that task and other workers to clean up
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_notify('pulp_worker_cancel', %s)", (str(task.pk),))
        cursor.execute("NOTIFY pulp_worker_wakeup")
    return task


def cancel_task_group(task_group_id):
    """
    Cancel the task group that is represented by the given task_group_id.

    This method attempts to cancel all tasks in the task group.

    Args:
        task_group_id (str): The ID of the task group you wish to cancel

    Raises:
        TaskGroup.DoesNotExist: If a task group with given task_group_id does not exist
    """
    task_group = TaskGroup.objects.get(pk=task_group_id)
    task_group.all_tasks_dispatched = True
    task_group.save(update_fields=["all_tasks_dispatched"])

    TASK_RUNNING_STATES = (TASK_STATES.RUNNING, TASK_STATES.WAITING)
    tasks = task_group.tasks.filter(state__in=TASK_RUNNING_STATES).values_list("pk", flat=True)
    for task_id in tasks:
        try:
            cancel_task(task_id)
        except RuntimeError:
            pass
    return task_group
