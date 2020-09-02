# coding=utf-8
"""Utilities for Pulpcore tests."""
from functools import partial
from time import sleep
from unittest import SkipTest

from pulp_smash import config, selectors
from pulp_smash.pulp3.bindings import monitor_task
from pulp_smash.pulp3.utils import require_pulp_3, require_pulp_plugins
from pulpcore.client.pulpcore import (
    ApiClient,
    OrphansApi,
    TaskGroupsApi,
)


cfg = config.get_config()
configuration = cfg.get_bindings_config()


def set_up_module():
    """Skip tests Pulp 3 isn't under test or if pulpcore isn't installed."""
    require_pulp_3(SkipTest)
    require_pulp_plugins({"pulpcore"}, SkipTest)


skip_if = partial(selectors.skip_if, exc=SkipTest)  # pylint:disable=invalid-name
"""The ``@skip_if`` decorator, customized for unittest.

:func:`pulp_smash.selectors.skip_if` is test runner agnostic. This function is
identical, except that ``exc`` has been set to ``unittest.SkipTest``.
"""

core_client = ApiClient(configuration)
task_groups = TaskGroupsApi(core_client)


def monitor_task_group(tg_href):
    """Polls the task group tasks until the tasks are in a completed state.

    Args:
        tg_href(str): the href of the task group to monitor

    Returns:
        pulpcore.client.pulpcore.TaskGroup: the bindings TaskGroup object
    """
    tg = task_groups.read(tg_href)
    while not tg.all_tasks_dispatched or (tg.waiting + tg.running) > 0:
        sleep(2)
        tg = task_groups.read(tg_href)
    if (tg.failed + tg.skipped + tg.canceled) > 0:
        print(f"The task group failed: {tg}")
        exit()
    else:
        print("The task group was successful.")
        return tg


def delete_orphans():
    """Delete orphans through bindings."""
    response = OrphansApi(core_client).delete()
    monitor_task(response.task)
