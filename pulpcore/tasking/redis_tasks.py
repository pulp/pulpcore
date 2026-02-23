"""
Task dispatch functions for Redis-based worker implementation.

This module contains dispatch logic specific to the Redis worker that uses
Redis distributed locks for task coordination.
"""

import contextvars
import logging
import sys
from asgiref.sync import sync_to_async

from pulpcore.app.models import Task, TaskGroup, AppStatus
from pulpcore.app.redis_connection import get_redis_connection
from pulpcore.app.util import get_domain
from pulpcore.app.contexts import with_task_context, awith_task_context
from pulpcore.constants import TASK_STATES, TASK_FINAL_STATES
from pulpcore.tasking.redis_locks import (
    acquire_locks,
    extract_task_resources,
    get_task_lock_key,
    safe_release_task_locks,
    async_safe_release_task_locks,
)
from pulpcore.tasking.tasks import (
    called_from_content_app,
    get_function_name,
    get_version,
    get_resources,
    get_task_payload,
    get_task_function,
    aget_task_function,
    log_task_start,
    log_task_completed,
    log_task_failed,
    using_workdir,
)
from pulpcore.tasking.kafka import send_task_notification


_logger = logging.getLogger(__name__)

# Redis key prefix for task cancellation
REDIS_CANCEL_PREFIX = "pulp:task:cancel:"


def publish_cancel_signal(task_id):
    """
    Publish a cancellation signal for a task via Redis.

    Args:
        task_id (str): The task ID to cancel

    Returns:
        bool: True if signal was published, False otherwise
    """
    redis_conn = get_redis_connection()

    try:
        # Publish to the task-specific cancellation channel
        cancel_key = f"{REDIS_CANCEL_PREFIX}{task_id}"
        # Set a value with expiration (24 hours) in case worker missed it
        redis_conn.setex(cancel_key, 86400, "cancel")
        _logger.info("Published cancellation signal for task %s", task_id)
        return True
    except Exception as e:
        _logger.error("Error publishing cancellation signal for task %s: %s", task_id, e)
        return False


def check_cancel_signal(task_id):
    """
    Check if a cancellation signal exists for a task.

    Args:
        task_id (str): The task ID to check

    Returns:
        bool: True if cancellation signal exists, False otherwise
    """
    redis_conn = get_redis_connection()

    try:
        cancel_key = f"{REDIS_CANCEL_PREFIX}{task_id}"
        return redis_conn.exists(cancel_key) > 0
    except Exception as e:
        _logger.error("Error checking cancellation signal for task %s: %s", task_id, e)
        return False


def clear_cancel_signal(task_id):
    """
    Clear a cancellation signal for a task.

    Args:
        task_id (str): The task ID to clear cancellation signal for
    """
    redis_conn = get_redis_connection()

    try:
        cancel_key = f"{REDIS_CANCEL_PREFIX}{task_id}"
        redis_conn.delete(cancel_key)
        _logger.debug("Cleared cancellation signal for task %s", task_id)
    except Exception as e:
        _logger.error("Error clearing cancellation signal for task %s: %s", task_id, e)


def cancel_task(task_id):
    """
    Cancel a task using Redis-based signaling.

    This method cancels only the task with given task_id, not the spawned tasks.
    This also updates task's state to 'canceling'.

    Args:
        task_id (str): The ID of the task you wish to cancel

    Returns:
        Task: The task object

    Raises:
        Task.DoesNotExist: If a task with given task_id does not exist
    """
    task = Task.objects.select_related("pulp_domain").get(pk=task_id)

    if task.state in TASK_FINAL_STATES:
        # If the task is already done, just stop.
        _logger.debug(
            "Task [%s] in domain: %s already in a final state: %s",
            task_id,
            task.pulp_domain.name,
            task.state,
        )
        return task

    _logger.info("Canceling task: %s in domain: %s", task_id, task.pulp_domain.name)

    # This is the only valid transition without holding the task lock.
    task.set_canceling()

    if task.app_lock is None:
        # Task was WAITING — no worker is executing it.
        # Set app_lock so set_canceled() ownership check passes.
        Task.objects.filter(pk=task.pk).update(app_lock=AppStatus.objects.current())
        task.app_lock = AppStatus.objects.current()
        task.set_canceled()
    else:
        # Task is RUNNING — signal the supervising worker.
        publish_cancel_signal(task.pk)

    return task


def cancel_task_group(task_group_id):
    """
    Cancel the task group that is represented by the given task_group_id using Redis.

    This method attempts to cancel all tasks in the task group.

    Args:
        task_group_id (str): The ID of the task group you wish to cancel

    Returns:
        TaskGroup: The task group object

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


def execute_task(task):
    """Redis-aware task execution that releases Redis locks for immediate tasks."""
    # This extra stack is needed to isolate the current_task ContextVar
    contextvars.copy_context().run(_execute_task, task)


def _execute_task(task):
    try:
        with with_task_context(task):
            task.set_running()
            domain = get_domain()
            exception_info = None
            result = None

            # Execute task and capture result or exception
            try:
                log_task_start(task, domain)
                task_function = get_task_function(task)
                result = task_function()
            except Exception:
                exc_type, exc, tb = sys.exc_info()
                exception_info = (exc_type, exc, tb)

            # Release locks BEFORE transitioning to final state
            # This ensures resources are freed even if we crash
            # during state transition
            safe_release_task_locks(task)

            # NOW transition to final state after locks are released
            if exception_info:
                exc_type, exc, tb = exception_info
                task.set_failed(exc, tb)
                log_task_failed(task, exc_type, exc, tb, domain)
                send_task_notification(task)
                return None
            else:
                task.set_completed(result)
                log_task_completed(task, domain)
                send_task_notification(task)
                return result
    finally:
        # Safety net: release locks if we failed before reaching the normal
        # release point (e.g., during set_running, set_failed, or set_completed)
        if safe_release_task_locks(task):
            _logger.warning(
                "SAFETY NET: Task %s releasing all locks in "
                "finally block (this shouldn't normally happen)",
                task.pk,
            )


async def aexecute_task(task):
    """Redis-aware async task execution that releases Redis locks for immediate tasks."""
    # This extra stack is needed to isolate the current_task ContextVar
    await contextvars.copy_context().run(_aexecute_task, task)


async def _aexecute_task(task):
    try:
        async with awith_task_context(task):
            await sync_to_async(task.set_running)()
            domain = get_domain()
            exception_info = None
            result = None

            # Execute task and capture result or exception
            try:
                task_coroutine_fn = await aget_task_function(task)
                result = await task_coroutine_fn()
            except Exception:
                exc_type, exc, tb = sys.exc_info()
                exception_info = (exc_type, exc, tb)

            # Release locks BEFORE transitioning to final state
            await async_safe_release_task_locks(task)

            # NOW transition to final state after locks are released
            if exception_info:
                exc_type, exc, tb = exception_info
                await sync_to_async(task.set_failed)(exc, tb)
                log_task_failed(task, exc_type, exc, tb, domain)
                send_task_notification(task)
                return None
            else:
                await sync_to_async(task.set_completed)(result)
                log_task_completed(task, domain)
                send_task_notification(task)
                return result
    finally:
        # Safety net: release locks if we failed before reaching the normal
        # release point (e.g., during set_running, set_failed, or set_completed)
        if await async_safe_release_task_locks(task):
            _logger.warning(
                "SAFETY NET (async): Task %s releasing all locks "
                "in finally block (this shouldn't normally happen)",
                task.pk,
            )


def are_resources_available(task: Task) -> bool:
    """
    Atomically try to acquire task lock and resource locks for immediate task.

    Resource conflicts are handled by Redis lock acquisition - if another task
    holds conflicting resource locks, acquire_locks() will fail atomically.

    Args:
        task: The task to acquire locks for.

    Returns:
        bool: True if all locks were acquired, False otherwise.
    """
    redis_conn = get_redis_connection()

    # Extract resources from task
    exclusive_resources, shared_resources = extract_task_resources(task)

    # Use AppStatus.current() to get a worker identifier for the lock value
    # For immediate tasks, we use a special identifier
    current_app = AppStatus.objects.current()
    lock_owner = current_app.name if current_app else f"immediate-{task.pk}"

    # Build task lock key
    task_lock_key = get_task_lock_key(task.pk)

    try:
        # Atomically acquire task lock + all resource locks
        blocked_resource_list = acquire_locks(
            redis_conn, lock_owner, task_lock_key, exclusive_resources, shared_resources
        )

        if not blocked_resource_list:
            # All locks acquired successfully
            _logger.debug(
                "Successfully acquired task lock and all resource locks for immediate task %s",
                task.pk,
            )
            return True
        else:
            # Failed to acquire locks
            _logger.debug(
                "Failed to acquire locks for immediate task %s (blocked: %s)",
                task.pk,
                blocked_resource_list,
            )
            return False

    except Exception as e:
        _logger.error("Error acquiring locks for immediate task %s: %s", task.pk, e)
        return False


async def async_are_resources_available(task: Task) -> bool:
    """
    Atomically try to acquire task lock and resource locks for immediate task (async version).

    Resource conflicts are handled by Redis lock acquisition - if another task
    holds conflicting resource locks, acquire_locks() will fail atomically.

    Args:
        task: The task to acquire locks for.

    Returns:
        bool: True if all locks were acquired, False otherwise.
    """
    redis_conn = get_redis_connection()

    # Extract resources from task
    exclusive_resources, shared_resources = extract_task_resources(task)

    # Use AppStatus.current() to get a worker identifier for the lock value
    # For immediate tasks, we use a special identifier
    current_app = await sync_to_async(AppStatus.objects.current)()
    lock_owner = current_app.name if current_app else f"immediate-{task.pk}"

    # Build task lock key
    task_lock_key = get_task_lock_key(task.pk)

    try:
        # Atomically acquire task lock + all resource locks
        blocked_resource_list = await sync_to_async(acquire_locks)(
            redis_conn, lock_owner, task_lock_key, exclusive_resources, shared_resources
        )

        if not blocked_resource_list:
            # All locks acquired successfully
            _logger.debug(
                "Successfully acquired task lock and all resource locks for immediate task %s",
                task.pk,
            )
            return True
        else:
            # Failed to acquire locks
            _logger.debug(
                "Failed to acquire locks for immediate task %s (blocked: %s)",
                task.pk,
                blocked_resource_list,
            )
            return False

    except Exception as e:
        _logger.error("Error acquiring locks for immediate task %s: %s", task.pk, e)
        return False


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
    Enqueue a message to Pulp workers with Redis-based resource locking.

    This version uses Redis distributed locks instead of PostgreSQL advisory locks.

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

    execute_now = immediate and not called_from_content_app()
    assert deferred or immediate, "A task must be at least `deferred` or `immediate`."
    function_name = get_function_name(func)
    versions = get_version(versions, function_name)
    _, resources = get_resources(exclusive_resources, shared_resources, immediate)
    app_lock = None if not execute_now else AppStatus.objects.current()  # Lazy evaluation...
    task_payload = get_task_payload(
        function_name, task_group, args, kwargs, resources, versions, immediate, deferred, app_lock
    )
    task = Task.objects.create(**task_payload)
    if execute_now:
        # Try to atomically acquire task lock and resource locks
        # are_resources_available() now acquires ALL locks atomically
        if are_resources_available(task):
            # All locks acquired successfully
            # Proceed with execution
            current_app = AppStatus.objects.current()
            lock_owner = current_app.name if current_app else f"immediate-{task.pk}"
            try:
                with using_workdir():
                    execute_task(task)
            except Exception:
                # Release locks if using_workdir() failed before
                # execute_task() had a chance to run and release them
                safe_release_task_locks(task, lock_owner)
                raise
        elif deferred:
            # Locks not available, defer to worker
            # Clear app_lock so workers can pick this up
            # No locks were acquired (atomic operation failed), so nothing to clean up
            Task.objects.filter(pk=task.pk).update(app_lock=None)
            task.app_lock = None
        else:
            # Can't acquire locks and can't be deferred - cancel task
            # No locks were acquired, so just set state
            task.set_canceling()
            task.set_canceled(TASK_STATES.CANCELED, "Resources temporarily unavailable.")
    return task


async def adispatch(
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
    """Async version of Redis-based dispatch."""
    execute_now = immediate and not called_from_content_app()
    assert deferred or immediate, "A task must be at least `deferred` or `immediate`."
    function_name = get_function_name(func)
    versions = get_version(versions, function_name)
    _, resources = get_resources(exclusive_resources, shared_resources, immediate)
    app_lock = None if not execute_now else AppStatus.objects.current()  # Lazy evaluation...
    task_payload = get_task_payload(
        function_name, task_group, args, kwargs, resources, versions, immediate, deferred, app_lock
    )
    task = await Task.objects.acreate(**task_payload)
    if execute_now:
        # Try to atomically acquire task lock and resource locks
        # async_are_resources_available() now acquires ALL locks atomically
        if await async_are_resources_available(task):
            # All locks acquired successfully
            # Proceed with execution
            current_app = await sync_to_async(AppStatus.objects.current)()
            lock_owner = current_app.name if current_app else f"immediate-{task.pk}"
            try:
                with using_workdir():
                    await aexecute_task(task)
            except Exception:
                # Release locks if using_workdir() failed before
                # aexecute_task() had a chance to run and release them
                await async_safe_release_task_locks(task, lock_owner)
                raise
        elif deferred:
            # Locks not available, defer to worker
            # Clear app_lock so workers can pick this up
            # No locks were acquired (atomic operation failed), so nothing to clean up
            await Task.objects.filter(pk=task.pk).aupdate(app_lock=None)
            task.app_lock = None
        else:
            # Can't acquire locks and can't be deferred - cancel task
            # No locks were acquired, so just set state
            await sync_to_async(task.set_canceling)()
            await sync_to_async(task.set_canceled)(
                TASK_STATES.CANCELED, "Resources temporarily unavailable."
            )
    return task
