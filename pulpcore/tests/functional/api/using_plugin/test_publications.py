import unittest

from pulp_smash import config
from pulp_smash.pulp3.bindings import delete_orphans, monitor_task

from pulp_smash.pulp3.utils import (
    gen_repo,
    get_content,
)

from pulpcore.client.pulp_file import (
    FileFilePublication,
    PublicationsFileApi,
    RemotesFileApi,
    RepositoriesFileApi,
    RepositorySyncURL,
)
from pulpcore.client.pulp_file.exceptions import ApiException

from pulpcore.tests.functional.api.using_plugin.constants import (
    FILE_MANY_FIXTURE_MANIFEST_URL,
    FILE_CONTENT_NAME,
)
from pulpcore.tests.functional.api.using_plugin.utils import (
    gen_file_client,
    gen_file_remote,
)


class ContentInPublicationViewTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        """Create class-wide variables."""
        cls.cfg = config.get_config()
        cls.file_client = gen_file_client()
        cls.repo_api = RepositoriesFileApi(cls.file_client)
        cls.publication_api = PublicationsFileApi(cls.file_client)
        cls.remote_api = RemotesFileApi(cls.file_client)

    @classmethod
    def tearDownClass(cls):
        delete_orphans()

    def test_all(self):
        """Create two publications and check view filter."""
        repo = self.repo_api.create(gen_repo())
        self.addCleanup(self.repo_api.delete, repo.pulp_href)

        remote = self.remote_api.create(gen_file_remote())
        self.addCleanup(self.remote_api.delete, remote.pulp_href)

        # Sync and update repository data.
        repo_sync_data = RepositorySyncURL(remote=remote.pulp_href)
        sync_response = self.repo_api.sync(repo.pulp_href, repo_sync_data)
        monitor_task(sync_response.task)
        repo = self.repo_api.read(repo.pulp_href)

        # Test content doesn't exists.
        non_existant_content_href = (
            "/pulp/api/v3/content/file/files/c4ed74cf-a806-490d-a25f-94c3c3dd2dd7/"
        )
        with self.assertRaises(ApiException) as ctx:
            self.publication_api.list(content=non_existant_content_href)
        self.assertEqual(ctx.exception.status, 400)

        # Test not published content.
        content_href = get_content(repo.to_dict())[FILE_CONTENT_NAME][0]["pulp_href"]
        self.assertEqual(self.publication_api.list(content=content_href).to_dict()["count"], 0)

        # Publication
        publication_data = FileFilePublication(repository=repo.pulp_href)
        publication_response = self.publication_api.create(publication_data)
        task_response = monitor_task(publication_response.task)
        publication = self.publication_api.read(task_response.created_resources[0])
        self.addCleanup(self.publication_api.delete, publication.pulp_href)

        # Second publication
        repo_second = self.repo_api.create(gen_repo())
        self.addCleanup(self.repo_api.delete, repo_second.pulp_href)

        body = gen_file_remote(url=FILE_MANY_FIXTURE_MANIFEST_URL)
        remote_second = self.remote_api.create(body)
        self.addCleanup(self.remote_api.delete, remote_second.pulp_href)

        repo_second_sync_data = RepositorySyncURL(remote=remote_second.pulp_href)
        sync_response = self.repo_api.sync(repo_second.pulp_href, repo_second_sync_data)
        monitor_task(sync_response.task)
        repo_second = self.repo_api.read(repo_second.pulp_href)

        publication_data = FileFilePublication(repository=repo_second.pulp_href)
        publication_response = self.publication_api.create(publication_data)
        task_response = monitor_task(publication_response.task)
        publication_second = self.publication_api.read(task_response.created_resources[0])
        self.addCleanup(self.publication_api.delete, publication_second.pulp_href)

        # Test there are two publications
        self.assertEqual(self.publication_api.list().count, 2)

        # Test content match publication
        self.assertEqual(self.publication_api.list(content=content_href).count, 1)
        self.assertEqual(
            self.publication_api.list(content=content_href).results[0].repository_version,
            repo.latest_version_href,
        )
