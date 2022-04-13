"""Tests related to the workers."""
import pytest
import unittest
from datetime import datetime, timedelta
from random import choice
from time import sleep

from pulp_smash import api, config, utils
from pulp_smash.pulp3.constants import WORKER_PATH
from requests.exceptions import HTTPError

from pulpcore.tests.functional.utils import skip_if


_DYNAMIC_WORKER_ATTRS = ("last_heartbeat", "current_task")
"""Worker attributes that are dynamically set by Pulp, not set by a user."""


class WorkersTestCase(unittest.TestCase):
    """Test actions over workers."""

    @classmethod
    def setUpClass(cls):
        """Create an API Client."""
        cls.cfg = config.get_config()
        cls.client = api.Client(cls.cfg, api.json_handler)
        cls.worker = {}

    def test_01_read_all_workers(self):
        """Read all workers.

        Pick a random worker to be used for the next assertions.
        """
        workers = self.client.get(WORKER_PATH)["results"]
        for worker in workers:
            for key, val in worker.items():
                if key in _DYNAMIC_WORKER_ATTRS:
                    continue
                with self.subTest(key=key):
                    self.assertIsNotNone(val)
        self.worker.update(choice(workers))

    @skip_if(bool, "worker", False)
    def test_02_read_worker(self):
        """Read a worker by its pulp_href."""
        worker = self.client.get(self.worker["pulp_href"])
        for key, val in self.worker.items():
            if key in _DYNAMIC_WORKER_ATTRS:
                continue
            with self.subTest(key=key):
                self.assertEqual(worker[key], val)

    @skip_if(bool, "worker", False)
    def test_02_read_workers(self):
        """Read a worker by its name."""
        page = self.client.get(WORKER_PATH, params={"name": self.worker["name"]})
        self.assertEqual(len(page["results"]), 1)
        for key, val in self.worker.items():
            if key in _DYNAMIC_WORKER_ATTRS:
                continue
            with self.subTest(key=key):
                self.assertEqual(page["results"][0][key], val)

    @skip_if(bool, "worker", False)
    def test_03_positive_filters(self):
        """Read a worker using a set of query parameters."""
        page = self.client.get(
            WORKER_PATH,
            params={
                "last_heartbeat__gte": self.worker["last_heartbeat"],
                "name": self.worker["name"],
            },
        )
        self.assertEqual(
            len(page["results"]), 1, "Expected: {}. Got: {}.".format([self.worker], page["results"])
        )
        for key, val in self.worker.items():
            if key in _DYNAMIC_WORKER_ATTRS:
                continue
            with self.subTest(key=key):
                self.assertEqual(page["results"][0][key], val)

    @skip_if(bool, "worker", False)
    def test_04_negative_filters(self):
        """Read a worker with a query that does not match any worker."""
        page = self.client.get(
            WORKER_PATH,
            params={
                "last_heartbeat__gte": str(datetime.now() + timedelta(days=1)),
                "name": self.worker["name"],
            },
        )
        self.assertEqual(len(page["results"]), 0)

    @skip_if(bool, "worker", False)
    def test_05_http_method(self):
        """Use an HTTP method different than GET.

        Assert an error is raised.
        """
        with self.assertRaises(HTTPError):
            self.client.delete(self.worker["pulp_href"])


@pytest.fixture()
def task_schedule(cli_client):
    name = "test_schedule"
    task_name = "pulpcore.app.tasks.test.dummy_task"
    utils.execute_pulpcore_python(
        cli_client,
        "from django.utils.timezone import now;"
        "from datetime import timedelta;"
        "from pulpcore.app.models import TaskSchedule;"
        "dispatch_interval = timedelta(seconds=4);"
        "next_dispatch = now() + dispatch_interval;"
        "TaskSchedule("
        f"    name='{name}', task_name='{task_name}', "
        "    dispatch_interval=dispatch_interval, next_dispatch=next_dispatch"
        ").save();",
    )
    yield {"name": name, "task_name": task_name}
    utils.execute_pulpcore_python(
        cli_client,
        "from pulpcore.app.models import TaskSchedule;"
        f"TaskSchedule.objects.get(name='{name}').delete();",
    )


@pytest.mark.parallel
def test_task_schedule(task_schedule, task_schedules_api_client):
    """Test that a worker will schedule a task roughly at a given time."""
    # Worker TTL is configured to 30s, therefore they will have a heartbeat each 10s (6 bpm). The
    # task is scheduled 4s in the future to give us time to invesitgate the state before and after.
    # 15s later we can be sure it was scheduled (as long as at least one worker is running).

    result = task_schedules_api_client.list(name=task_schedule["name"])
    assert result.count == 1
    ts = task_schedules_api_client.read(task_schedule_href=result.results[0].pulp_href)
    assert ts.name == task_schedule["name"]
    assert ts.task_name == task_schedule["task_name"]
    assert ts.last_task is None
    # At least a worker heartbeat is needed
    for i in range(15):
        sleep(1)
        ts = task_schedules_api_client.read(task_schedule_href=result.results[0].pulp_href)
        if ts.last_task is not None:
            break
    assert ts.last_task is not None
