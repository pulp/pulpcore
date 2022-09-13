from unittest import TestCase
from time import sleep

from pulpcore.client.pulpcore import ApiClient, OrphansApi, TasksApi, TaskGroupsApi

try:
    from pulpcore.client.pulpcore import OrphansCleanupApi
except ImportError:  # This is only available in pulpcore 3.14+
    OrphansCleanupApi = None

from pulpcore.tests.suite.api import _get_sleep_time
from pulpcore.tests.suite.config import get_config


cfg = get_config()
SLEEP_TIME = _get_sleep_time()
configuration = cfg.get_bindings_config()
pulpcore_client = ApiClient(configuration)
tasks = TasksApi(pulpcore_client)
task_groups = TaskGroupsApi(pulpcore_client)


class PulpTestCase(TestCase):
    """Pulp customized test case."""

    def doCleanups(self):
        """
        Execute all cleanup functions and waits the deletion tasks.

        Normally called for you after tearDown.
        """
        output = super().doCleanups()
        running_tasks = tasks.list(state="running", name__contains="delete")
        while running_tasks.count:
            sleep(SLEEP_TIME)
            running_tasks = tasks.list(state="running", name__contains="delete")
        return output


class PulpTaskError(Exception):
    """Exception to describe task errors."""

    def __init__(self, task):
        """Provide task info to exception."""
        description = task.to_dict()["error"]["description"]
        super().__init__(self, f"Pulp task failed ({description})")
        self.task = task


class PulpTaskGroupError(Exception):
    """Exception to describe task group errors."""

    def __init__(self, task_group):
        """Provide task info to exception."""
        super().__init__(self, f"Pulp task group failed ({task_group})")
        self.task_group = task_group


def monitor_task(task_href):
    """Polls the Task API until the task is in a completed state.

    Prints the task details and a success or failure message. Exits on failure.

    Args:
        task_href(str): The href of the task to monitor

    Returns:
        list[str]: List of hrefs that identify resource created by the task

    """
    completed = ["completed", "failed", "canceled"]
    task = tasks.read(task_href)
    while task.state not in completed:
        sleep(SLEEP_TIME)
        task = tasks.read(task_href)

    if task.state != "completed":
        raise PulpTaskError(task=task)

    return task


def monitor_task_group(tg_href):
    """Polls the task group tasks until the tasks are in a completed state.

    Args:
        tg_href(str): the href of the task group to monitor

    Returns:
        pulpcore.client.pulpcore.TaskGroup: the bindings TaskGroup object
    """
    tg = task_groups.read(tg_href)

    while not tg.all_tasks_dispatched or (tg.waiting + tg.running) > 0:
        sleep(SLEEP_TIME)
        tg = task_groups.read(tg_href)

    if (tg.failed + tg.skipped + tg.canceled) > 0:
        raise PulpTaskGroupError(task_group=tg)

    return tg


def delete_orphans(orphan_protection_time=0):
    """Delete orphans through bindings."""
    if OrphansCleanupApi:
        response = OrphansCleanupApi(pulpcore_client).cleanup(
            {"orphan_protection_time": orphan_protection_time}
        )
    else:
        response = OrphansApi(pulpcore_client).delete()
    monitor_task(response.task)
