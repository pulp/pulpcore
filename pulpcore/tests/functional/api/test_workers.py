# coding=utf-8
"""Tests related to the workers."""
import time
import unittest
from datetime import datetime, timedelta
from random import choice

from pulp_smash import api, cli, config
from pulp_smash.pulp3.constants import STATUS_PATH, WORKER_PATH
from requests.exceptions import HTTPError

from pulpcore.tests.functional.utils import set_up_module as setUpModule  # noqa:F401
from pulpcore.tests.functional.utils import skip_if

_DYNAMIC_WORKER_ATTRS = ('last_heartbeat',)
"""Worker attributes that are dynamically set by Pulp, not set by a user."""


class WorkersTestCase(unittest.TestCase):
    """Test actions over workers.

    This test targets the following issues:

    * `Pulp #3143 <https://pulp.plan.io/issues/3143>`_
    * `Pulp Smash #945 <https://github.com/PulpQE/pulp-smash/issues/945>`_
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
        workers = self.client.get(WORKER_PATH)['results']
        for worker in workers:
            for key, val in worker.items():
                with self.subTest(key=key):
                    self.assertIsNotNone(val)
        self.worker.update(choice(workers))

    @skip_if(bool, 'worker', False)
    def test_02_read_worker(self):
        """Read a worker by its pulp_href."""
        worker = self.client.get(self.worker['pulp_href'])
        for key, val in self.worker.items():
            if key in _DYNAMIC_WORKER_ATTRS:
                continue
            with self.subTest(key=key):
                self.assertEqual(worker[key], val)

    @skip_if(bool, 'worker', False)
    def test_02_read_workers(self):
        """Read a worker by its name."""
        page = self.client.get(WORKER_PATH, params={
            'name': self.worker['name']
        })
        self.assertEqual(len(page['results']), 1)
        for key, val in self.worker.items():
            if key in _DYNAMIC_WORKER_ATTRS:
                continue
            with self.subTest(key=key):
                self.assertEqual(page['results'][0][key], val)

    @skip_if(bool, 'worker', False)
    def test_03_positive_filters(self):
        """Read a worker using a set of query parameters."""
        page = self.client.get(WORKER_PATH, params={
            'last_heartbeat__gte': self.worker['last_heartbeat'],
            'name': self.worker['name'],
            'online': self.worker['online'],
            'missing': self.worker['missing'],
        })
        self.assertEqual(
            len(page['results']), 1,
            'Expected: {}. Got: {}.'.format([self.worker], page['results'])
        )
        for key, val in self.worker.items():
            if key in _DYNAMIC_WORKER_ATTRS:
                continue
            with self.subTest(key=key):
                self.assertEqual(page['results'][0][key], val)

    @skip_if(bool, 'worker', False)
    def test_04_negative_filters(self):
        """Read a worker with a query that does not match any worker."""
        page = self.client.get(WORKER_PATH, params={
            'last_heartbeat__gte': str(datetime.now() + timedelta(days=1)),
            'name': self.worker['name'],
            'online': self.worker['online'],
            'missing': self.worker['missing'],
        })
        self.assertEqual(len(page['results']), 0)

    @skip_if(bool, 'worker', False)
    def test_05_http_method(self):
        """Use an HTTP method different than GET.

        Assert an error is raised.
        """
        with self.assertRaises(HTTPError):
            self.client.delete(self.worker['pulp_href'])


class OfflineWorkerTestCase(unittest.TestCase):
    """Test actions over offline workers.

    This test targets the following issues:

    * `Pulp #2659 <https://pulp.plan.io/issues/2659>`_
    * `Pulp Smash #877 <https://github.com/PulpQE/pulp-smash/issues/877>`_
    """

    @classmethod
    def setUpClass(cls):
        """Create an API Client and a ServiceManager."""
        cls.cfg = config.get_config()
        cls.client = api.Client(cls.cfg, api.json_handler)
        cls.svc_mgr = cli.ServiceManager(cls.cfg, cls.cfg.get_hosts('api')[0])
        cls.worker = {}
        if not cls.svc_mgr.is_active(['pulpcore-worker@*']):
            raise unittest.SkipTest(
                'These tests require pulp workers running on systemd'
            )

    def test_01_start_new_worker(self):
        """Start a new worker to be used in next assertions."""
        self.svc_mgr.start(['pulpcore-worker@99'])
        time.sleep(2)
        workers = self.client.get(
            WORKER_PATH, params={'online': True}
        )['results']
        for worker in workers:
            if 'worker-99' in worker['name']:
                self.worker.update(worker)
                break
        self.assertNotEqual({}, self.worker)
        self.assertIn('resource-worker-99', self.worker['name'])

    @skip_if(bool, 'worker', False)
    def test_02_stop_worker(self):
        """Stop the worker and assert it is offline."""
        self.svc_mgr.stop(['pulpcore-worker@99'])
        time.sleep(2)
        worker = self.client.get(self.worker['pulp_href'])
        self.assertEqual(worker['online'], False)

    @skip_if(bool, 'worker', False)
    def test_03_status_api_omits_offline_worker(self):
        """Status API doesn't show offline workers."""
        online_workers = self.client.get(STATUS_PATH)['online_workers']
        self.assertNotIn(
            self.worker['pulp_href'],
            [worker['pulp_href'] for worker in online_workers]
        )

    @skip_if(bool, 'worker', False)
    def test_03_read_all_workers(self):
        """Worker API shows all workers including offline."""
        workers = self.client.get(WORKER_PATH)['results']
        self.assertIn(
            self.worker['pulp_href'],
            [worker['pulp_href'] for worker in workers]
        )

    @skip_if(bool, 'worker', False)
    def test_03_filter_offline_worker(self):
        """Worker API filter only offline workers."""
        workers = self.client.get(
            WORKER_PATH, params={'online': False}
        )['results']
        self.assertIn(
            self.worker['pulp_href'],
            [worker['pulp_href'] for worker in workers]
        )
