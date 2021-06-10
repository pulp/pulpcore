"""Tests that publish file plugin repositories."""
import unittest
from random import choice

from pulp_smash import config
from pulp_smash.pulp3.bindings import monitor_task
from pulp_smash.pulp3.utils import (
    gen_repo,
    get_content,
    gen_distribution,
    get_versions,
)

from pulpcore.tests.functional.api.using_plugin.constants import FILE_CONTENT_NAME
from pulpcore.tests.functional.api.using_plugin.utils import (
    gen_file_client,
    gen_file_remote,
)
from pulpcore.tests.functional.utils import set_up_module as setUpModule  # noqa:F401

from pulpcore.client.pulp_file import (
    DistributionsFileApi,
    PublicationsFileApi,
    RepositoriesFileApi,
    RepositoryAddRemoveContent,
    RepositorySyncURL,
    RemotesFileApi,
    FileFilePublication,
)
from pulpcore.client.pulp_file.exceptions import ApiException


class PublishAnyRepoVersionTestCase(unittest.TestCase):
    """Test whether a particular repository version can be published.

    This test targets the following issues:

    * `Pulp #3324 <https://pulp.plan.io/issues/3324>`_
    * `Pulp Smash #897 <https://github.com/pulp/pulp-smash/issues/897>`_
    """

    @classmethod
    def setUpClass(cls):
        """Create class-wide variables."""
        cls.cfg = config.get_config()

        client = gen_file_client()
        cls.repo_api = RepositoriesFileApi(client)
        cls.remote_api = RemotesFileApi(client)
        cls.publications = PublicationsFileApi(client)
        cls.distributions = DistributionsFileApi(client)

    def setUp(self):
        """Create a new repository before each test."""
        manifest_path = "/pulp/content/pulp_pre_upgrade_test/PULP_MANIFEST"
        url = self.cfg.get_content_host_base_url() + manifest_path
        body = gen_file_remote(url=url)
        remote = self.remote_api.create(body)

        repo = self.repo_api.create(gen_repo())

        repository_sync_data = RepositorySyncURL(remote=remote.pulp_href)
        sync_response = self.repo_api.sync(repo.pulp_href, repository_sync_data)
        monitor_task(sync_response.task)

        self.repo = self.repo_api.read(repo.pulp_href)

    def test_all(self):
        """Test whether a particular repository version can be published.

        1. Create a repository with at least 2 repository versions.
        2. Create a publication by supplying the latest ``repository_version``.
        3. Assert that the publication ``repository_version`` attribute points
           to the latest repository version.
        4. Create a publication by supplying the non-latest ``repository_version``.
        5. Create distribution.
        6. Assert that the publication ``repository_version`` attribute points
           to the supplied repository version.
        7. Assert that an exception is raised when providing two different
           repository versions to be published at same time.
        """
        # Step 1
        for file_content in get_content(self.repo.to_dict())[FILE_CONTENT_NAME]:
            repository_modify_data = RepositoryAddRemoveContent(
                remove_content_units=[file_content["pulp_href"]]
            )
            modify_response = self.repo_api.modify(self.repo.pulp_href, repository_modify_data)
            monitor_task(modify_response.task)
        version_hrefs = tuple(ver["pulp_href"] for ver in get_versions(self.repo.to_dict()))
        non_latest = choice(version_hrefs[:-1])

        # Step 2
        publish_data = FileFilePublication(repository=self.repo.pulp_href)
        publication = self.create_publication(publish_data)

        # Step 3
        self.assertEqual(publication.repository_version, version_hrefs[-1])

        # Step 4
        publish_data = FileFilePublication(repository_version=non_latest)
        publication = self.create_publication(publish_data)

        # Step 5
        body = gen_distribution()
        body["base_path"] = "pulp_post_upgrade_test"
        body["publication"] = publication.pulp_href

        distribution_response = self.distributions.create(body)
        created_resources = monitor_task(distribution_response.task).created_resources
        distribution = self.distributions.read(created_resources[0])

        # Step 6
        self.assertEqual(publication.repository_version, non_latest)

        # Step 7
        with self.assertRaises(ApiException):
            body = {"repository": self.repo.pulp_href, "repository_version": non_latest}
            self.publications.create(body)

        # Step 8
        url = self.cfg.get_content_host_base_url() + "/pulp/content/pulp_post_upgrade_test/"
        self.assertEqual(url, distribution.base_url, url)

    def test_custom_manifest(self):
        """Test whether a repository version can be published with a specified manifest."""
        publish_data = FileFilePublication(repository=self.repo.pulp_href)
        publication = self.create_publication(publish_data)
        self.assertEqual(publication.manifest, "PULP_MANIFEST")

        publish_data = FileFilePublication(repository=self.repo.pulp_href, manifest="listing")
        publication = self.create_publication(publish_data)
        self.assertEqual(publication.manifest, "listing")

    def create_publication(self, publish_data):
        """Create a new publication from the passed data."""
        publish_response = self.publications.create(publish_data)
        created_resources = monitor_task(publish_response.task).created_resources
        publication_href = created_resources[0]
        return self.publications.read(publication_href)
