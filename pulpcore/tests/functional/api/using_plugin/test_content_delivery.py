"""Tests related to content delivery."""
import hashlib
import unittest
from random import choice
from urllib.parse import urljoin

from pulp_smash import api, config, utils
from pulp_smash.pulp3.bindings import delete_orphans, monitor_task, PulpTestCase
from pulp_smash.pulp3.constants import ON_DEMAND_DOWNLOAD_POLICIES
from pulp_smash.pulp3.utils import (
    download_content_unit,
    gen_distribution,
    gen_repo,
    get_content,
    sync,
)
from requests import HTTPError

from pulpcore.client.pulp_file import (
    PublicationsFileApi,
    RemotesFileApi,
    RepositoriesFileApi,
    RepositorySyncURL,
    DistributionsFileApi,
)
from pulpcore.tests.functional.api.using_plugin.constants import (
    FILE_CONTENT_NAME,
    FILE_DISTRIBUTION_PATH,
    FILE_FIXTURE_URL,
    FILE_FIXTURE_MANIFEST_URL,
    FILE_FIXTURE_WITH_MISSING_FILES_MANIFEST_URL,
    FILE_REMOTE_PATH,
    FILE_REPO_PATH,
)
from pulpcore.tests.functional.api.using_plugin.utils import (
    create_file_publication,
    gen_file_remote,
    gen_file_client,
)
from pulpcore.tests.functional.api.using_plugin.utils import (  # noqa:F401
    set_up_module as setUpModule,
)


class ContentDeliveryTestCase(unittest.TestCase):
    """Content delivery breaks when delete remote - lazy download policy.

    Deleting a remote that was used in a sync with either the on_demand or
    streamed options can break published data. Specifically, clients who want
    to fetch content that a remote was providing access to would begin to
    404. Recreating a remote and re-triggering a sync will cause these broken
    units to recover again.

    This test targets the following issue:

    * `Pulp #4464 <https://pulp.plan.io/issues/4464>`_
    """

    def test_content_remote_delete(self):
        """Assert that an HTTP error is raised when remote is deleted.

        Also verify that the content can be downloaded from Pulp once the
        remote is recreated and another sync is triggered.
        """
        cfg = config.get_config()
        delete_orphans()
        client = api.Client(cfg, api.page_handler)

        repo = client.post(FILE_REPO_PATH, gen_repo())
        self.addCleanup(client.delete, repo["pulp_href"])

        body = gen_file_remote(policy=choice(ON_DEMAND_DOWNLOAD_POLICIES))
        remote = client.post(FILE_REMOTE_PATH, body)

        # Sync the repository using a lazy download policy.
        sync(cfg, remote, repo)
        repo = client.get(repo["pulp_href"])

        publication = create_file_publication(cfg, repo)
        self.addCleanup(client.delete, publication["pulp_href"])

        # Delete the remote.
        client.delete(remote["pulp_href"])

        body = gen_distribution()
        body["publication"] = publication["pulp_href"]
        distribution = client.using_handler(api.task_handler).post(FILE_DISTRIBUTION_PATH, body)
        self.addCleanup(client.delete, distribution["pulp_href"])

        unit_path = choice(
            [content_unit["relative_path"] for content_unit in get_content(repo)[FILE_CONTENT_NAME]]
        )

        # Assert that an HTTP error is raised when one to fetch content from
        # the distribution once the remote was removed.
        with self.assertRaises(HTTPError) as ctx:
            download_content_unit(cfg, distribution, unit_path)
        for key in ("not", "found"):
            self.assertIn(key, ctx.exception.response.reason.lower())

        # Recreating a remote and re-triggering a sync will cause these broken
        # units to recover again.
        body = gen_file_remote(policy=choice(ON_DEMAND_DOWNLOAD_POLICIES))
        remote = client.post(FILE_REMOTE_PATH, body)
        self.addCleanup(client.delete, remote["pulp_href"])

        sync(cfg, remote, repo)
        repo = client.get(repo["pulp_href"])

        content = download_content_unit(cfg, distribution, unit_path)
        pulp_hash = hashlib.sha256(content).hexdigest()

        fixtures_hash = hashlib.sha256(
            utils.http_get(urljoin(FILE_FIXTURE_URL, unit_path))
        ).hexdigest()

        self.assertEqual(pulp_hash, fixtures_hash)


class RemoteArtifactUpdateTestCase(PulpTestCase):
    @classmethod
    def setUpClass(cls):
        """Clean out Pulp before testing."""
        delete_orphans()
        client = gen_file_client()
        cls.repo_api = RepositoriesFileApi(client)
        cls.remote_api = RemotesFileApi(client)
        cls.publication_api = PublicationsFileApi(client)
        cls.distributions_api = DistributionsFileApi(client)
        cls.cfg = config.get_config()

    def tearDown(self):
        """Clean up Pulp after testing."""
        self.doCleanups()
        delete_orphans()

    def test_remote_artifact_url_update(self):
        """Test that downloading on_demand content works after a repository layout change."""

        FILE_NAME = "1.iso"

        # 1. Create a remote, repository and distribution - remote URL has links that should 404
        remote_config = gen_file_remote(
            policy="on_demand", url=FILE_FIXTURE_WITH_MISSING_FILES_MANIFEST_URL
        )
        remote = self.remote_api.create(remote_config)
        self.addCleanup(self.remote_api.delete, remote.pulp_href)

        repo = self.repo_api.create(gen_repo(autopublish=True, remote=remote.pulp_href))
        self.addCleanup(self.repo_api.delete, repo.pulp_href)

        body = gen_distribution(repository=repo.pulp_href)
        distribution_response = self.distributions_api.create(body)
        created_resources = monitor_task(distribution_response.task).created_resources
        distribution = self.distributions_api.read(created_resources[0])
        self.addCleanup(self.distributions_api.delete, distribution.pulp_href)

        # 2. Sync the repository, verify that downloading artifacts fails
        repository_sync_data = RepositorySyncURL(remote=remote.pulp_href)

        sync_response = self.repo_api.sync(repo.pulp_href, repository_sync_data)
        monitor_task(sync_response.task)

        with self.assertRaises(HTTPError):
            download_content_unit(self.cfg, distribution.to_dict(), FILE_NAME)

        # 3. Update the remote URL with one that works, sync again, check that downloading
        # artifacts works.
        update_response = self.remote_api.update(
            remote.pulp_href, gen_file_remote(policy="on_demand", url=FILE_FIXTURE_MANIFEST_URL)
        )
        monitor_task(update_response.task)

        sync_response = self.repo_api.sync(repo.pulp_href, repository_sync_data)
        monitor_task(sync_response.task)

        content = download_content_unit(self.cfg, distribution.to_dict(), FILE_NAME)
        pulp_hash = hashlib.sha256(content).hexdigest()

        fixtures_hash = hashlib.sha256(
            utils.http_get(urljoin(FILE_FIXTURE_URL, FILE_NAME))
        ).hexdigest()

        self.assertEqual(pulp_hash, fixtures_hash)
