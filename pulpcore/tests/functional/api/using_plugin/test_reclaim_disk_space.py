"""Tests that perform actions over reclaim disk space."""
from pulp_smash import config
from pulp_smash.pulp3.bindings import monitor_task, PulpTestCase
from pulp_smash.pulp3.utils import (
    gen_repo,
    get_content,
    gen_distribution,
    download_content_unit,
)
from pulpcore.client.pulpcore import (
    ArtifactsApi,
    OrphansCleanupApi,
    RepositoriesReclaimSpaceApi,
)
from pulpcore.client.pulp_file import (
    FileFilePublication,
    PublicationsFileApi,
    RepositoriesFileApi,
    RepositorySyncURL,
    RemotesFileApi,
    DistributionsFileApi,
)
from pulpcore.tests.functional.api.using_plugin.constants import FILE_CONTENT_NAME
from pulpcore.tests.functional.api.using_plugin.utils import (
    gen_file_client,
    gen_file_remote,
)
from pulpcore.tests.functional.utils import core_client


class ReclaimSpaceTestCase(PulpTestCase):
    """
    Test whether repository content can be reclaimed.
    Subsequently, confirm that artifact is correctly re-downloaded in sync
    task or when streamed to the client (this is true only for synced content, not uploaded.)
    """

    @classmethod
    def setUpClass(cls):
        """Create class-wide variables."""
        cls.cfg = config.get_config()
        cls.client = gen_file_client()
        cls.orphans_api = OrphansCleanupApi(core_client)
        cls.reclaim_api = RepositoriesReclaimSpaceApi(core_client)
        cls.artifacts_api = ArtifactsApi(core_client)
        cls.publication_api = PublicationsFileApi(cls.client)
        cls.distributions_api = DistributionsFileApi(cls.client)
        cls.repo_api = RepositoriesFileApi(cls.client)
        cls.remote_api = RemotesFileApi(cls.client)

        orphans_response = cls.orphans_api.cleanup({"orphan_protection_time": 0})
        monitor_task(orphans_response.task)

    def tearDown(self):
        """Clean created resources."""
        # Runs any delete tasks and waits for them to complete
        self.doCleanups()
        orphans_response = self.orphans_api.cleanup({"orphan_protection_time": 0})
        monitor_task(orphans_response.task)

    def test_reclaim_immediate_content(self):
        """
        Test whether immediate repository content can be reclaimed
        and then re-populated back after sync.
        """
        repo = self.repo_api.create(gen_repo())
        self.addCleanup(self.repo_api.delete, repo.pulp_href)

        remote = self.remote_api.create(gen_file_remote())
        self.addCleanup(self.remote_api.delete, remote.pulp_href)

        # sync the repository with immediate policy
        repository_sync_data = RepositorySyncURL(remote=remote.pulp_href)
        sync_response = self.repo_api.sync(repo.pulp_href, repository_sync_data)
        monitor_task(sync_response.task)

        # reclaim disk space
        reclaim_response = self.reclaim_api.reclaim({"repo_hrefs": [repo.pulp_href]})
        monitor_task(reclaim_response.task)

        # assert no artifacts left
        artifacts = self.artifacts_api.list().count
        self.assertEqual(artifacts, 0)

        # sync repo again
        repository_sync_data = RepositorySyncURL(remote=remote.pulp_href)
        sync_response = self.repo_api.sync(repo.pulp_href, repository_sync_data)
        monitor_task(sync_response.task)

        # assert re-sync populated missing artifacts
        artifacts = self.artifacts_api.list().count
        self.assertGreater(artifacts, 0)
        self.addCleanup(self.orphans_api.cleanup, {"orphan_protection_time": 0})

    def test_reclaim_on_demand_content(self):
        """
        Test whether on_demand repository content can be reclaimed
        and then re-populated back after client request.
        """
        repo, distribution = self._repo_sync_distribute(policy="on_demand")

        artifacts_before_download = self.artifacts_api.list().count
        content = get_content(repo.to_dict())[FILE_CONTENT_NAME][0]
        download_content_unit(self.cfg, distribution.to_dict(), content["relative_path"])

        artifacts = self.artifacts_api.list().count
        self.assertGreater(artifacts, artifacts_before_download)

        # reclaim disk space
        reclaim_response = self.reclaim_api.reclaim({"repo_hrefs": [repo.pulp_href]})
        monitor_task(reclaim_response.task)

        artifacts_after_reclaim = self.artifacts_api.list().count
        content = get_content(repo.to_dict())[FILE_CONTENT_NAME]
        download_content_unit(self.cfg, distribution.to_dict(), content[0]["relative_path"])

        artifacts = self.artifacts_api.list().count
        self.assertGreater(artifacts, artifacts_after_reclaim)

    def test_immediate_reclaim_becomes_on_demand(self):
        """Tests if immediate content becomes like on_demand content after reclaim."""
        repo, distribution = self._repo_sync_distribute()

        artifacts_before_reclaim = self.artifacts_api.list().count
        self.assertGreater(artifacts_before_reclaim, 0)
        content = get_content(repo.to_dict())[FILE_CONTENT_NAME][0]
        # Populate cache
        download_content_unit(self.cfg, distribution.to_dict(), content["relative_path"])

        reclaim_response = self.reclaim_api.reclaim({"repo_hrefs": [repo.pulp_href]})
        monitor_task(reclaim_response.task)

        artifacts_after_reclaim = self.artifacts_api.list().count
        self.assertLess(artifacts_after_reclaim, artifacts_before_reclaim)

        download_content_unit(self.cfg, distribution.to_dict(), content["relative_path"])
        artifacts_after_download = self.artifacts_api.list().count
        # Downloading a reclaimed content will increase the artifact count by 1
        self.assertEqual(artifacts_after_download, artifacts_after_reclaim + 1)
        # But only 1 extra artifact will be downloaded, so still less than after immediate sync
        self.assertLess(artifacts_after_download, artifacts_before_reclaim)

    def _repo_sync_distribute(self, policy="immediate"):
        """Helper to create & populate a repository and distribute it."""
        repo = self.repo_api.create(gen_repo())
        self.addCleanup(self.repo_api.delete, repo.pulp_href)

        # sync the repository with passed in policy
        body = gen_file_remote(**{"policy": policy})
        remote = self.remote_api.create(body)
        self.addCleanup(self.remote_api.delete, remote.pulp_href)

        # sync repo
        repository_sync_data = RepositorySyncURL(remote=remote.pulp_href)
        sync_response = self.repo_api.sync(repo.pulp_href, repository_sync_data)
        monitor_task(sync_response.task)
        repo = self.repo_api.read(repo.pulp_href)

        # Publication
        publication_data = FileFilePublication(repository=repo.pulp_href)
        publication_response = self.publication_api.create(publication_data)
        task_response = monitor_task(publication_response.task)
        publication = self.publication_api.read(task_response.created_resources[0])
        self.addCleanup(self.publication_api.delete, publication.pulp_href)

        # Distribution
        body = gen_distribution()
        body["publication"] = publication.pulp_href
        distribution_response = self.distributions_api.create(body)
        created_resources = monitor_task(distribution_response.task).created_resources
        distribution = self.distributions_api.read(created_resources[0])
        self.addCleanup(self.distributions_api.delete, distribution.pulp_href)

        return repo, distribution
