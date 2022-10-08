"""Utilities for Pulpcore tests."""
import aiohttp

from functools import partial
from time import sleep
from unittest import SkipTest

from pulp_smash import config, selectors

from pulpcore.client.pulpcore import ApiClient, TasksApi, TaskGroupsApi


async def get_response(url):
    async with aiohttp.ClientSession() as session:
        return await session.get(url)


skip_if = partial(selectors.skip_if, exc=SkipTest)  # pylint:disable=invalid-name
"""The ``@skip_if`` decorator, customized for unittest.

:func:`pulp_smash.selectors.skip_if` is test runner agnostic. This function is
identical, except that ``exc`` has been set to ``unittest.SkipTest``.
"""

cfg = config.get_config()
configuration = cfg.get_bindings_config()
core_client = ApiClient(configuration)
SLEEP_TIME = 0.3  # Taken from pulp_smash
tasks = TasksApi(core_client)
task_groups = TaskGroupsApi(core_client)


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
