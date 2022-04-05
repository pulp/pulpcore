"""Tests related to content cache."""
import requests
import unittest
from urllib.parse import urljoin

from pulp_smash.pulp3.bindings import monitor_task
from pulp_smash.pulp3.utils import gen_distribution, gen_repo

from .constants import PULP_CONTENT_BASE_URL
from pulpcore.tests.functional.api.using_plugin.utils import (
    gen_file_client,
    gen_file_remote,
)
from pulpcore.client.pulp_file import (
    ContentFilesApi,
    RepositoryAddRemoveContent,
    RepositorySyncURL,
    RepositoriesFileApi,
    RemotesFileApi,
    PublicationsFileApi,
    FileFilePublication,
    DistributionsFileApi,
    PatchedfileFileDistribution,
)
from pulpcore.tests.functional.api.using_plugin.utils import (  # noqa:F401
    set_up_module as setUpModule,
)
from pulpcore.tests.functional.api.utils import get_redis_status

is_redis_connected = get_redis_status()


@unittest.skipUnless(is_redis_connected, "Could not connect to the Redis server")
class ContentCacheTestCache(unittest.TestCase):
    """Test content cache"""

    @classmethod
    def setUpClass(cls):
        """Sets up class"""
        client = gen_file_client()
        cls.cont_api = ContentFilesApi(client)
        cls.repo_api = RepositoriesFileApi(client)
        cls.remote_api = RemotesFileApi(client)
        cls.pub_api = PublicationsFileApi(client)
        cls.dis_api = DistributionsFileApi(client)

    def setUp(self):
        self.repo = self.repo_api.create(gen_repo(autopublish=True))
        self.remote = self.remote_api.create(gen_file_remote())

        body = RepositorySyncURL(remote=self.remote.pulp_href)
        created = monitor_task(self.repo_api.sync(self.repo.pulp_href, body).task).created_resources
        self.repo = self.repo_api.read(self.repo.pulp_href)
        self.pub1 = self.pub_api.read(created[1])
        body = FileFilePublication(repository=self.repo.pulp_href)
        self.pub2 = self.pub_api.read(
            monitor_task(self.pub_api.create(body).task).created_resources[0]
        )
        self.pub3 = []
        response = self.dis_api.create(gen_distribution(repository=self.repo.pulp_href))
        self.distro = self.dis_api.read(monitor_task(response.task).created_resources[0])
        self.distro2 = []
        self.url = urljoin(PULP_CONTENT_BASE_URL, f"{self.distro.base_path}/")

    def tearDown(self):
        a = self.remote_api.delete(self.remote.pulp_href).task
        b = self.dis_api.delete(self.distro.pulp_href).task
        for task_href in [a, b]:
            monitor_task(task_href)

    def test_content_cache_workflow(self):
        self._basic_cache_access()
        self._remove_repository_invalidates()
        self._restore_repository()
        self._multiple_distributions()
        self._invalidate_multiple_distributions()
        self._delete_distribution_invalidates_one()
        self._delete_extra_pub_doesnt_invalidate()
        self._delete_served_pub_does_invalidate()
        self._delete_repo_invalidates()
        self._no_error_when_accessing_invalid_file()

    def _basic_cache_access(self):
        """Checks responses are cached for content"""
        files = ["", "", "PULP_MANIFEST", "PULP_MANIFEST", "1.iso", "1.iso"]
        for i, file in enumerate(files):
            self.assertEqual((200, "HIT" if i % 2 == 1 else "MISS"), self._check_cache(file), file)

    def _remove_repository_invalidates(self):
        """Checks removing repository from distribution invalidates the cache"""
        body = PatchedfileFileDistribution(repository="")
        monitor_task(self.dis_api.partial_update(self.distro.pulp_href, body).task)
        files = ["", "PULP_MANIFEST", "1.iso"]
        for file in files:
            self.assertEqual((404, None), self._check_cache(file), file)

    def _restore_repository(self):
        """Checks that responses are cacheable after repository is added back"""
        body = PatchedfileFileDistribution(repository=self.repo.pulp_href)
        monitor_task(self.dis_api.partial_update(self.distro.pulp_href, body).task)
        files = ["", "", "PULP_MANIFEST", "PULP_MANIFEST", "1.iso", "1.iso"]
        for i, file in enumerate(files):
            self.assertEqual((200, "HIT" if i % 2 == 1 else "MISS"), self._check_cache(file), file)

    def _multiple_distributions(self):
        """Add a new distribution and check that its responses are cached separately"""
        response = self.dis_api.create(gen_distribution(repository=self.repo.pulp_href))
        self.distro2.append(self.dis_api.read(monitor_task(response.task).created_resources[0]))
        url = urljoin(PULP_CONTENT_BASE_URL, f"{self.distro2[0].base_path}/")
        files = ["", "", "PULP_MANIFEST", "PULP_MANIFEST", "1.iso", "1.iso"]
        for i, file in enumerate(files):
            self.assertEqual(
                (200, "HIT" if i % 2 == 1 else "MISS"), self._check_cache(file, url), file
            )

    def _invalidate_multiple_distributions(self):
        """Test that updating a repository pointed by multiple distributions invalidates all"""
        url = urljoin(PULP_CONTENT_BASE_URL, f"{self.distro2[0].base_path}/")
        cfile = self.cont_api.list(
            relative_path="1.iso", repository_version=self.repo.latest_version_href
        ).results[0]
        body = RepositoryAddRemoveContent(remove_content_units=[cfile.pulp_href])
        response = monitor_task(self.repo_api.modify(self.repo.pulp_href, body).task)
        self.pub3.append(self.pub_api.read(response.created_resources[1]))
        files = ["", "", "PULP_MANIFEST", "PULP_MANIFEST", "2.iso", "2.iso"]
        for i, file in enumerate(files):
            self.assertEqual((200, "HIT" if i % 2 == 1 else "MISS"), self._check_cache(file), file)
            self.assertEqual(
                (200, "HIT" if i % 2 == 1 else "MISS"), self._check_cache(file, url), file
            )

    def _delete_distribution_invalidates_one(self):
        """Tests that deleting one distribution sharing a repository only invalidates its cache"""
        url = urljoin(PULP_CONTENT_BASE_URL, f"{self.distro2[0].base_path}/")
        monitor_task(self.dis_api.delete(self.distro2[0].pulp_href).task)
        files = ["", "PULP_MANIFEST", "2.iso"]
        for file in files:
            self.assertEqual((200, "HIT"), self._check_cache(file), file)
            self.assertEqual((404, None), self._check_cache(file, url), file)

    def _delete_extra_pub_doesnt_invalidate(self):
        """Test that deleting a publication not being served doesn't invalidate cache"""
        self.pub_api.delete(self.pub2.pulp_href)
        files = ["", "PULP_MANIFEST", "2.iso"]
        for file in files:
            self.assertEqual((200, "HIT"), self._check_cache(file), file)

    def _delete_served_pub_does_invalidate(self):
        """Test that deleting the serving publication does invalidate the cache"""
        # Reverts back to serving self.pub1
        self.pub_api.delete(self.pub3[0].pulp_href)
        files = ["", "", "PULP_MANIFEST", "PULP_MANIFEST", "2.iso", "2.iso"]
        for i, file in enumerate(files):
            self.assertEqual((200, "HIT" if i % 2 == 1 else "MISS"), self._check_cache(file), file)

    def _delete_repo_invalidates(self):
        """Tests that deleting a repository invalidates the cache"""
        monitor_task(self.repo_api.delete(self.repo.pulp_href).task)
        files = ["", "PULP_MANIFEST", "2.iso"]
        for file in files:
            self.assertEqual((404, None), self._check_cache(file), file)

    def _no_error_when_accessing_invalid_file(self):
        """Tests that accessing a file that doesn't exist on content app gives 404"""
        files = ["invalid", "another/bad-one", "DNE/"]
        url = PULP_CONTENT_BASE_URL
        for file in files:
            self.assertEqual((404, None), self._check_cache(file, url=url), file)

    def _check_cache(self, file, url=None):
        """Helper to check if cache miss or hit"""
        url = urljoin(url or self.url, file)
        r = requests.get(url)
        if r.history:
            r = r.history[0]
            return 200 if r.status_code == 302 else r.status_code, r.headers.get("X-PULP-CACHE")
        return r.status_code, r.headers.get("X-PULP-CACHE")
