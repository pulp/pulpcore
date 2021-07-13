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
        cls.repo = cls.repo_api.create(gen_repo(autopublish=True))
        cls.remote = cls.remote_api.create(gen_file_remote())
        body = RepositorySyncURL(remote=cls.remote.pulp_href)
        created = monitor_task(cls.repo_api.sync(cls.repo.pulp_href, body).task).created_resources
        cls.repo = cls.repo_api.read(cls.repo.pulp_href)
        cls.pub1 = cls.pub_api.read(created[1])
        body = FileFilePublication(repository=cls.repo.pulp_href)
        cls.pub2 = cls.pub_api.read(
            monitor_task(cls.pub_api.create(body).task).created_resources[0]
        )
        cls.pub3 = []
        response = cls.dis_api.create(gen_distribution(repository=cls.repo.pulp_href))
        cls.distro = cls.dis_api.read(monitor_task(response.task).created_resources[0])
        cls.distro2 = []
        cls.url = urljoin(PULP_CONTENT_BASE_URL, f"{cls.distro.base_path}/")

    @classmethod
    def tearDownClass(cls):
        """Tears the class down"""
        cls.remote_api.delete(cls.remote.pulp_href)
        cls.dis_api.delete(cls.distro.pulp_href)

    def test_01_basic_cache_access(self):
        """Checks responses are cached for content"""
        files = ["", "", "PULP_MANIFEST", "PULP_MANIFEST", "1.iso", "1.iso"]
        for i, file in enumerate(files):
            self.assertEqual((200, "HIT" if i % 2 == 1 else "MISS"), self.check_cache(file), file)

    def test_02_remove_repository_invalidates(self):
        """Checks removing repository from distribution invalidates the cache"""
        body = PatchedfileFileDistribution(repository="")
        monitor_task(self.dis_api.partial_update(self.distro.pulp_href, body).task)
        files = ["", "PULP_MANIFEST", "1.iso"]
        for file in files:
            self.assertEqual((404, None), self.check_cache(file), file)

    def test_03_restore_repository(self):
        """Checks that responses are cacheable after repository is added back"""
        body = PatchedfileFileDistribution(repository=self.repo.pulp_href)
        monitor_task(self.dis_api.partial_update(self.distro.pulp_href, body).task)
        files = ["", "", "PULP_MANIFEST", "PULP_MANIFEST", "1.iso", "1.iso"]
        for i, file in enumerate(files):
            self.assertEqual((200, "HIT" if i % 2 == 1 else "MISS"), self.check_cache(file), file)

    def test_04_multiple_distributions(self):
        """Add a new distribution and check that its responses are cached separately"""
        response = self.dis_api.create(gen_distribution(repository=self.repo.pulp_href))
        self.distro2.append(self.dis_api.read(monitor_task(response.task).created_resources[0]))
        url = urljoin(PULP_CONTENT_BASE_URL, f"{self.distro2[0].base_path}/")
        files = ["", "", "PULP_MANIFEST", "PULP_MANIFEST", "1.iso", "1.iso"]
        for i, file in enumerate(files):
            self.assertEqual(
                (200, "HIT" if i % 2 == 1 else "MISS"), self.check_cache(file, url), file
            )

    def test_05_invalidate_multiple_distributions(self):
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
            self.assertEqual((200, "HIT" if i % 2 == 1 else "MISS"), self.check_cache(file), file)
            self.assertEqual(
                (200, "HIT" if i % 2 == 1 else "MISS"), self.check_cache(file, url), file
            )

    def test_06_delete_distribution_invalidates_one(self):
        """Tests that deleting one distribution sharing a repository only invalidates its cache"""
        url = urljoin(PULP_CONTENT_BASE_URL, f"{self.distro2[0].base_path}/")
        monitor_task(self.dis_api.delete(self.distro2[0].pulp_href).task)
        files = ["", "PULP_MANIFEST", "2.iso"]
        for file in files:
            self.assertEqual((200, "HIT"), self.check_cache(file), file)
            self.assertEqual((404, None), self.check_cache(file, url), file)

    def test_07_delete_extra_pub_doesnt_invalidate(self):
        """Test that deleting a publication not being served doesn't invalidate cache"""
        self.pub_api.delete(self.pub2.pulp_href)
        files = ["", "PULP_MANIFEST", "2.iso"]
        for file in files:
            self.assertEqual((200, "HIT"), self.check_cache(file), file)

    def test_08_delete_served_pub_does_invalidate(self):
        """Test that deleting the serving publication does invalidate the cache"""
        # Reverts back to serving self.pub1
        self.pub_api.delete(self.pub3[0].pulp_href)
        files = ["", "", "PULP_MANIFEST", "PULP_MANIFEST", "2.iso", "2.iso"]
        for i, file in enumerate(files):
            self.assertEqual((200, "HIT" if i % 2 == 1 else "MISS"), self.check_cache(file), file)

    def test_09_delete_repo_invalidates(self):
        """Tests that deleting a repository invalidates the cache"""
        monitor_task(self.repo_api.delete(self.repo.pulp_href).task)
        files = ["", "PULP_MANIFEST", "2.iso"]
        for file in files:
            self.assertEqual((404, None), self.check_cache(file), file)

    def test_10_no_error_when_accessing_invalid_file(self):
        """Tests that accessing a file that doesn't exist on content app gives 404"""
        files = ["invalid", "another/bad-one", "DNE/"]
        url = PULP_CONTENT_BASE_URL
        for file in files:
            self.assertEqual((404, None), self.check_cache(file, url=url), file)

    def check_cache(self, file, url=None):
        """Helper to check if cache miss or hit"""
        url = urljoin(url or self.url, file)
        r = requests.get(url)
        if r.history:
            r = r.history[0]
            return 200 if r.status_code == 302 else r.status_code, r.headers.get("X-PULP-CACHE")
        return r.status_code, r.headers.get("X-PULP-CACHE")
