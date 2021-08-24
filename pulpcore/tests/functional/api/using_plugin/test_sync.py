from pulp_smash.pulp3.bindings import delete_orphans, monitor_task, PulpTestCase
from pulp_smash.pulp3.utils import gen_repo

from pulpcore.tests.functional.api.using_plugin.utils import (
    gen_file_client,
    gen_file_remote,
)
from pulpcore.client.pulp_file import (
    ContentFilesApi,
    RepositorySyncURL,
    RepositoriesFileApi,
    RemotesFileApi,
)
from pulpcore.tests.functional.api.using_plugin.utils import (  # noqa:F401
    set_up_module as setUpModule,
)


class MultiplePolicySyncTestCase(PulpTestCase):
    """
    This test ensures that content artifacts are properly updated when syncing multiple
    times with different policies, specifically from 'on_demand' to 'immediate'

    This test targets the following issue:
    * `Pulp #9101 <https://pulp.plan.io/issues/9101>`_
    """

    @classmethod
    def setUpClass(cls):
        """Clean out Pulp before testing."""
        delete_orphans()
        client = gen_file_client()
        cls.cont_api = ContentFilesApi(client)
        cls.repo_api = RepositoriesFileApi(client)
        cls.remote_api = RemotesFileApi(client)

    def tearDown(self):
        """Clean up Pulp after testing."""
        self.doCleanups()
        delete_orphans()

    def test_ondemand_to_immediate_sync(self):
        """Checks that content artifacts are updated following on-demand -> immediate sync."""
        # Ensure that no content is present
        content_response = self.cont_api.list(limit=1)
        if content_response.count > 0:
            self.skipTest("Please remove all file content before running this test")

        # Create and sync repo w/ on_demand policy
        repo = self.repo_api.create(gen_repo())
        remote = self.remote_api.create(gen_file_remote(policy="on_demand"))
        body = RepositorySyncURL(remote=remote.pulp_href)
        monitor_task(self.repo_api.sync(repo.pulp_href, body).task)
        self.addCleanup(self.repo_api.delete, repo.pulp_href)
        self.addCleanup(self.remote_api.delete, remote.pulp_href)

        # Check content is present, but no artifacts are there
        content_response = self.cont_api.list()
        self.assertEqual(content_response.count, 3)
        for content in content_response.results:
            self.assertEqual(content.artifact, None)

        # Sync again w/ immediate policy
        remote = self.remote_api.create(gen_file_remote())
        body = RepositorySyncURL(remote=remote.pulp_href)
        monitor_task(self.repo_api.sync(repo.pulp_href, body).task)
        self.addCleanup(self.remote_api.delete, remote.pulp_href)

        # Check content is still present, but artifacts are now there
        content_response = self.cont_api.list()
        self.assertEqual(content_response.count, 3)
        for content in content_response.results:
            self.assertNotEqual(content.artifact, None)
