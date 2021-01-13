import json
import unittest
from uuid import uuid4

from pulp_smash import config
from pulp_smash.pulp3.bindings import monitor_task

from pulpcore.tests.functional.utils import set_up_module as setUpModule  # noqa:F401
from pulpcore.client.pulp_file import (
    ApiClient as FileApiClient,
    RepositoriesFileApi,
)
from pulpcore.client.pulp_file.exceptions import ApiException


class CRUDRepoTestCase(unittest.TestCase):
    """CRUD repositories."""

    @classmethod
    def setUpClass(cls):
        """Create class-wide variables."""
        cls.cfg = config.get_config()
        cls.repo = None

    def setUp(self):
        """Create an API client."""
        self.client = FileApiClient(self.cfg.get_bindings_config())
        self.repo_api = RepositoriesFileApi(self.client)

    def _create_repo(self, labels={}):
        attrs = {"name": str(uuid4())}
        if labels:
            attrs["pulp_labels"] = labels
        self.repo = self.repo_api.create(attrs)
        self.addCleanup(self.repo_api.delete, self.repo.pulp_href)

    def test_create_repo_with_labels(self):
        """Create repository with labels."""
        labels = {"maiar": "mithrandir"}
        self._create_repo(labels)
        self.assertEqual(labels, self.repo.pulp_labels)

    def test_add_repo_labels(self):
        """Update repository with labels."""
        labels = {"maiar": "mithrandir", "valar": "varda"}
        self._create_repo()

        resp = self.repo_api.partial_update(self.repo.pulp_href, {"pulp_labels": labels})
        monitor_task(resp.task)
        self.repo = self.repo_api.read(self.repo.pulp_href)
        self.assertEqual(labels, self.repo.pulp_labels)

    def test_update_repo_label(self):
        """Test updating an existing label."""
        labels = {"valar": "varda"}
        self._create_repo(labels)

        labels["valar"] = "manwe"

        resp = self.repo_api.partial_update(self.repo.pulp_href, {"pulp_labels": labels})
        monitor_task(resp.task)
        self.repo = self.repo_api.read(self.repo.pulp_href)
        self.assertEqual(labels, self.repo.pulp_labels)

    def test_unset_repo_label(self):
        """Test unsetting a repo label."""
        labels = {"maiar": "mithrandir", "valar": "varda"}
        self._create_repo(labels)

        labels.pop("valar")
        resp = self.repo_api.partial_update(self.repo.pulp_href, {"pulp_labels": labels})
        monitor_task(resp.task)
        self.repo = self.repo_api.read(self.repo.pulp_href)
        self.assertEqual(1, len(self.repo.pulp_labels))
        self.assertEqual(labels, self.repo.pulp_labels)

    def test_remove_all_repo_labels(self):
        """Test removing all labels."""
        labels = {"maiar": "mithrandir", "valar": "varda"}
        self._create_repo(labels)

        resp = self.repo_api.partial_update(self.repo.pulp_href, {"pulp_labels": {}})
        monitor_task(resp.task)
        self.repo = self.repo_api.read(self.repo.pulp_href)
        self.assertEqual(0, len(self.repo.pulp_labels))
        self.assertEqual({}, self.repo.pulp_labels)

    def test_model_partial_update(self):
        """Test that labels aren't unset accidentially with PATCH calls."""
        labels = {"maiar": "mithrandir", "valar": "varda"}
        self._create_repo(labels)

        resp = self.repo_api.partial_update(self.repo.pulp_href, {"name": str(uuid4())})
        monitor_task(resp.task)
        self.repo = self.repo_api.read(self.repo.pulp_href)
        self.assertEqual(labels, self.repo.pulp_labels)

    def test_invalid_label_type(self):
        """Test that label doesn't accept non-dicts"""
        with self.assertRaises(ApiException) as ae:
            self._create_repo("morgoth")  # str instead of dict

        self.assertEqual(400, ae.exception.status)
        self.assertTrue("pulp_labels" in json.loads(ae.exception.body))

    def test_invalid_labels(self):
        """Test that label keys and values are validated."""
        with self.assertRaises(ApiException) as ae:
            self._create_repo({"@": "maia"})

        self.assertEqual(400, ae.exception.status)
        self.assertTrue("pulp_labels" in json.loads(ae.exception.body))

        with self.assertRaises(ApiException) as ae:
            self._create_repo({"arda": "eru,illuvata"})

        self.assertEqual(400, ae.exception.status)
        self.assertTrue("pulp_labels" in json.loads(ae.exception.body))
