# coding=utf-8
"""Tests related to the workers."""
import unittest
from datetime import datetime, timedelta
from random import choice

from pulp_smash import api, config
from pulp_smash.pulp3.constants import WORKER_PATH
from requests.exceptions import HTTPError

from pulpcore.tests.functional.utils import set_up_module as setUpModule  # noqa:F401
from pulpcore.tests.functional.utils import skip_if

_DYNAMIC_WORKER_ATTRS = ("last_heartbeat",)
"""Worker attributes that are dynamically set by Pulp, not set by a user."""


class WorkersTestCase(unittest.TestCase):
    """Test actions over workers.

    This test targets the following issues:

    * `Pulp #3143 <https://pulp.plan.io/issues/3143>`_
    * `Pulp Smash #945 <https://github.com/pulp/pulp-smash/issues/945>`_
    """

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
