import asyncio
import backoff
import os
import signal
import time
from pulpcore.app.models import TaskGroup
from pulpcore.tasking.tasks import dispatch


def dummy_task():
    """Dummy task, that can be used in tests."""
    pass


def sleep(interval):
    time.sleep(interval)


async def asleep(interval):
    """Async function that sleeps."""
    await asyncio.sleep(interval)


@backoff.on_exception(backoff.expo, BaseException)
def gooey_task(interval):
    """A sleep task that tries to avoid being killed by ignoring all exceptions."""
    time.sleep(interval)


def dummy_group_task(inbetween=3, intervals=None):
    """A group task that dispatches 'interval' sleep tasks every 'inbetween' seconds.'"""
    intervals = intervals or range(5)
    task_group = TaskGroup.current()
    for interval in intervals:
        dispatch(sleep, args=(interval,), task_group=task_group)
        time.sleep(inbetween)


def missing_worker():
    """
    Simulates a worker crash by sending SIGKILL to parent process and itself.

    This task is used for testing worker cleanup behavior when a worker
    unexpectedly dies while executing a task.
    """
    parent_pid = os.getppid()
    current_pid = os.getpid()

    # Kill parent process (the worker)
    os.kill(parent_pid, signal.SIGKILL)

    # Kill current process (the task subprocess)
    os.kill(current_pid, signal.SIGKILL)


def failing_task(error_message="Task intentionally failed"):
    """
    A task that always raises a RuntimeError.

    This task is used for testing error handling in worker task execution.

    Args:
        error_message (str): The error message to include in the RuntimeError
    """
    raise RuntimeError(error_message)


async def afailing_task(error_message="Task intentionally failed"):
    """
    An async task that always raises a RuntimeError.

    This task is used for testing error handling in immediate task execution.

    Args:
        error_message (str): The error message to include in the RuntimeError
    """
    raise RuntimeError(error_message)
