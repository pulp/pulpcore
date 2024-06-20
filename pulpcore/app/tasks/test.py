import backoff
from pulpcore.app.models import TaskGroup
from pulpcore.tasking.tasks import dispatch


def dummy_task():
    """Dummy task, that can be used in tests."""
    pass


def sleep(interval):
    from time import sleep

    sleep(interval)


@backoff.on_exception(backoff.expo, BaseException)
def gooey_task(interval):
    """A sleep task that tries to avoid being killed by ignoring all exceptions."""
    from time import sleep

    sleep(interval)


def dummy_group_task(inbetween=3, intervals=None):
    """A group task that dispatches 'interval' sleep tasks every 'inbetween' seconds.'"""
    intervals = intervals or range(5)
    task_group = TaskGroup.current()
    for interval in intervals:
        dispatch(sleep, args=(interval,), task_group=task_group)
        sleep(inbetween)
    task_group.finish()
