"""Tests that perform actions over distributions."""
import csv
import hashlib
import unittest
from urllib.parse import urljoin

from pulp_smash import api, config, utils
from pulp_smash.pulp3.bindings import delete_orphans
from pulp_smash.pulp3.utils import (
    download_content_unit,
    gen_distribution,
    gen_repo,
    get_content,
    get_versions,
    modify_repo,
    sync,
)
from requests.exceptions import HTTPError

from pulpcore.client.pulp_file import (
    ContentFilesApi,
    DistributionsFileApi,
    FileFilePublication,
    PublicationsFileApi,
    RemotesFileApi,
    RepositoriesFileApi,
    RepositorySyncURL,
)
from pulpcore.tests.functional.api.using_plugin.constants import (
    FILE_CONTENT_NAME,
    FILE_DISTRIBUTION_PATH,
    FILE_FIXTURE_COUNT,
    FILE_REMOTE_PATH,
    FILE_URL,
    FILE_REPO_PATH,
)
from pulpcore.tests.functional.api.using_plugin.utils import (
    create_file_publication,
    gen_file_remote,
    gen_file_client,
    monitor_task,
)
from pulpcore.tests.functional.api.using_plugin.utils import set_up_module as setUpModule  # noqa
from pulpcore.tests.functional.api.using_plugin.utils import skip_if


class CRUDPublicationDistributionTestCase(unittest.TestCase):
    """CRUD Publication Distribution.

    This test targets the following issue:

    * `Pulp #4839 <https://pulp.plan.io/issues/4839>`_
    * `Pulp #4862 <https://pulp.plan.io/issues/4862>`_
    """

    @classmethod
    def setUpClass(cls):
        """Create class-wide variables."""
        cls.cfg = config.get_config()
        cls.client = api.Client(cls.cfg)
        cls.attr = (
            "name",
            "base_path",
        )
        cls.distribution = {}
        cls.publication = {}
        cls.remote = {}
        cls.repo = {}

    @classmethod
    def tearDownClass(cls):
        """Clean class-wide variables."""
        for resource in (cls.publication, cls.remote, cls.repo):
            if resource:
                cls.client.delete(resource["pulp_href"])

    def test_01_create(self):
        """Create a publication distribution.

        Do the following:

        1. Create a repository and 3 repository versions with at least 1 file
           content in it. Create a publication using the second repository
           version.
        2. Create a distribution with 'publication' field set to
           the publication from step (1).
        3. Assert the distribution got created correctly with the correct
           base_path, name, and publication. Assert that content guard is
           unset.
        4. Assert that publication has a 'distributions' reference to the
           distribution (it's backref).

        """
        self.repo.update(self.client.post(FILE_REPO_PATH, gen_repo()))
        self.remote.update(self.client.post(FILE_REMOTE_PATH, gen_file_remote()))
        # create 3 repository versions
        sync(self.cfg, self.remote, self.repo)
        self.repo = self.client.get(self.repo["pulp_href"])
        for file_content in get_content(self.repo)[FILE_CONTENT_NAME]:
            modify_repo(self.cfg, self.repo, remove_units=[file_content])

        self.repo = self.client.get(self.repo["pulp_href"])

        versions = get_versions(self.repo)

        self.publication.update(
            create_file_publication(self.cfg, self.repo, versions[1]["pulp_href"])
        )

        self.distribution.update(
            self.client.post(
                FILE_DISTRIBUTION_PATH, gen_distribution(publication=self.publication["pulp_href"])
            )
        )

        self.publication = self.client.get(self.publication["pulp_href"])

        # content_guard and repository parameters unset.
        for key, val in self.distribution.items():
            if key in ["content_guard", "repository"]:
                self.assertIsNone(val, self.distribution)
            else:
                self.assertIsNotNone(val, self.distribution)

        self.assertEqual(
            self.distribution["publication"], self.publication["pulp_href"], self.distribution
        )

        self.assertEqual(
            self.publication["distributions"][0], self.distribution["pulp_href"], self.publication
        )

    @skip_if(bool, "distribution", False)
    def test_02_read(self):
        """Read distribution by its href."""
        distribution = self.client.get(self.distribution["pulp_href"])
        for key, val in self.distribution.items():
            with self.subTest(key=key):
                self.assertEqual(distribution[key], val)

    @skip_if(bool, "distribution", False)
    def test_03_partially_update(self):
        """Update a distribution using PATCH."""
        for key in self.attr:
            with self.subTest(key=key):
                self.do_partially_update_attr(key)

    @skip_if(bool, "distribution", False)
    def test_03_fully_update(self):
        """Update a distribution using PUT."""
        for key in self.attr:
            with self.subTest(key=key):
                self.do_fully_update_attr(key)

    @skip_if(bool, "distribution", False)
    def test_04_delete_distribution(self):
        """Delete a distribution."""
        self.client.delete(self.distribution["pulp_href"])
        with self.assertRaises(HTTPError):
            self.client.get(self.distribution["pulp_href"])

    def do_fully_update_attr(self, attr):
        """Update a distribution attribute using HTTP PUT.

        :param attr: The name of the attribute to update.
        """
        distribution = self.client.get(self.distribution["pulp_href"])
        string = utils.uuid4()
        distribution[attr] = string
        self.client.put(distribution["pulp_href"], distribution)

        # verify the update
        distribution = self.client.get(distribution["pulp_href"])
        self.assertEqual(string, distribution[attr], distribution)

    def do_partially_update_attr(self, attr):
        """Update a distribution using HTTP PATCH.

        :param attr: The name of the attribute to update.
        """
        string = utils.uuid4()
        self.client.patch(self.distribution["pulp_href"], {attr: string})

        # Verify the update
        distribution = self.client.get(self.distribution["pulp_href"])
        self.assertEqual(string, distribution[attr], self.distribution)


class DistributionBasePathTestCase(unittest.TestCase):
    """Test possible values for ``base_path`` on a distribution.

    This test targets the following issues:

    * `Pulp #2987 <https://pulp.plan.io/issues/2987>`_
    * `Pulp #3412 <https://pulp.plan.io/issues/3412>`_
    * `Pulp #4882 <https://pulp.plan.io/issues/4882>`_
    * `Pulp Smash #906 <https://github.com/pulp/pulp-smash/issues/906>`_
    * `Pulp Smash #956 <https://github.com/pulp/pulp-smash/issues/956>`_
    """

    @classmethod
    def setUpClass(cls):
        """Create class-wide variables."""
        cls.cfg = config.get_config()
        cls.client = api.Client(cls.cfg)
        body = gen_distribution()
        body["base_path"] = body["base_path"].replace("-", "/")
        distribution = cls.client.post(FILE_DISTRIBUTION_PATH, body)
        cls.distribution = cls.client.get(distribution["pulp_href"])

    @classmethod
    def tearDownClass(cls):
        """Clean up resources."""
        cls.client.delete(cls.distribution["pulp_href"])

    def test_negative_create_using_spaces(self):
        """Test that spaces can not be part of ``base_path``."""
        self.try_create_distribution(base_path=utils.uuid4().replace("-", " "))
        self.try_update_distribution(base_path=utils.uuid4().replace("-", " "))

    def test_negative_create_using_begin_slash(self):
        """Test that slash cannot be in the begin of ``base_path``."""
        self.try_create_distribution(base_path="/" + utils.uuid4())
        self.try_update_distribution(base_path="/" + utils.uuid4())

    def test_negative_create_using_end_slash(self):
        """Test that slash cannot be in the end of ``base_path``."""
        self.try_create_distribution(base_path=utils.uuid4() + "/")
        self.try_update_distribution(base_path=utils.uuid4() + "/")

    def test_negative_create_using_non_unique_base_path(self):
        """Test that ``base_path`` can not be duplicated."""
        self.try_create_distribution(base_path=self.distribution["base_path"])

    def test_negative_create_using_overlapping_base_path(self):
        """Test that distributions can't have overlapping ``base_path``.

        See: `Pulp #2987`_.
        """
        base_path = self.distribution["base_path"].rsplit("/", 1)[0]
        self.try_create_distribution(base_path=base_path)

        base_path = "/".join((self.distribution["base_path"], utils.uuid4().replace("-", "/")))
        self.try_create_distribution(base_path=base_path)

    def try_create_distribution(self, **kwargs):
        """Unsuccessfully create a distribution.

        Merge the given kwargs into the body of the request.
        """
        body = gen_distribution()
        body.update(kwargs)
        with self.assertRaises(HTTPError) as ctx:
            self.client.post(FILE_DISTRIBUTION_PATH, body)

        self.assertIsNotNone(
            ctx.exception.response.json()["base_path"], ctx.exception.response.json()
        )

    def try_update_distribution(self, **kwargs):
        """Unsuccessfully update a distribution with HTTP PATCH.

        Use the given kwargs as the body of the request.
        """
        with self.assertRaises(HTTPError) as ctx:
            self.client.patch(self.distribution["pulp_href"], kwargs)

        self.assertIsNotNone(
            ctx.exception.response.json()["base_path"], ctx.exception.response.json()
        )


class ContentServePublicationDistributionTestCase(unittest.TestCase):
    """Verify that content is served from a publication distribution.

    Assert that published metadata and content is served from a publication
    distribution.

    This test targets the following issue:

    `Pulp #4847 <https://pulp.plan.io/issues/4847>`_
    """

    @classmethod
    def setUpClass(cls):
        """Create class-wide variables."""
        cls.cfg = config.get_config()
        cls.client = gen_file_client()

        cls.content_api = ContentFilesApi(cls.client)
        cls.repo_api = RepositoriesFileApi(cls.client)
        cls.remote_api = RemotesFileApi(cls.client)
        cls.publications_api = PublicationsFileApi(cls.client)
        cls.distributions_api = DistributionsFileApi(cls.client)

    def setUp(self):
        delete_orphans()

    def test_nonpublished_content_not_served(self):
        """Verify content that hasn't been published is not served."""
        # Create a repository
        self.repo = self.repo_api.create(gen_repo())
        self.addCleanup(self.repo_api.delete, self.repo.pulp_href)

        # Create a remote
        self.remote = self.remote_api.create(gen_file_remote())
        self.addCleanup(self.remote_api.delete, self.remote.pulp_href)

        # Sync the repository.
        repository_sync_data = RepositorySyncURL(remote=self.remote.pulp_href)
        sync_response = self.repo_api.sync(self.repo.pulp_href, repository_sync_data)
        monitor_task(sync_response.task)

        # Create a distribution.
        response = self.distributions_api.create(
            {"name": "foo", "base_path": "bar/foo", "repository": self.repo.pulp_href}
        )
        distribution_href = monitor_task(response.task).created_resources[0]
        self.distribution = self.distributions_api.read(distribution_href)
        self.addCleanup(self.distributions_api.delete, self.distribution.pulp_href)

    def test_content_served_on_demand(self):
        """Assert that on_demand content can be properly downloaded."""
        self.setup_download_test("on_demand")
        self.do_test_content_served()

    def test_content_served_immediate(self):
        """Assert that downloaded content can be properly downloaded."""
        self.setup_download_test("immediate")
        self.do_test_content_served()

    @unittest.skip("https://pulp.plan.io/issues/8865")
    def test_content_served_on_demand_with_range_request(self):
        """Assert that on_demand content can be properly downloaded with range requests."""
        self.setup_download_test("on_demand")
        self.do_range_request_download_test()

    def test_content_served_immediate_with_range_request(self):
        """Assert that downloaded content can be properly downloaded with range requests."""
        self.setup_download_test("immediate")
        self.do_range_request_download_test()

    def setup_download_test(self, policy):
        # Create a repository
        self.repo = self.repo_api.create(gen_repo())
        self.addCleanup(self.repo_api.delete, self.repo.pulp_href)

        # Create a remote
        self.remote = self.remote_api.create(gen_file_remote(policy=policy))
        self.addCleanup(self.remote_api.delete, self.remote.pulp_href)

        # Sync the repository.
        repository_sync_data = RepositorySyncURL(remote=self.remote.pulp_href)
        sync_response = self.repo_api.sync(self.repo.pulp_href, repository_sync_data)
        monitor_task(sync_response.task)

        # Create a publication.
        publish_data = FileFilePublication(repository=self.repo.pulp_href)
        publish_response = self.publications_api.create(publish_data)
        publication_href = monitor_task(publish_response.task).created_resources[0]
        self.addCleanup(self.publications_api.delete, publication_href)

        # Create a distribution.
        response = self.distributions_api.create(
            {"name": "foo", "base_path": "bar/foo", "publication": publication_href}
        )
        distribution_href = monitor_task(response.task).created_resources[0]
        self.distribution = self.distributions_api.read(distribution_href)
        self.addCleanup(self.distributions_api.delete, self.distribution.pulp_href)

    def do_test_content_served(self):
        file_path = "1.iso"

        req1 = download_content_unit(self.cfg, self.distribution.to_dict(), file_path)
        req2 = download_content_unit(self.cfg, self.distribution.to_dict(), file_path)
        fixtures_hash = hashlib.sha256(utils.http_get(urljoin(FILE_URL, file_path))).hexdigest()

        first_dl_hash = hashlib.sha256(req1).hexdigest()
        second_dl_hash = hashlib.sha256(req2).hexdigest()

        self.assertEqual(first_dl_hash, fixtures_hash)
        self.assertEqual(first_dl_hash, second_dl_hash)

        manifest = download_content_unit(self.cfg, self.distribution.to_dict(), "PULP_MANIFEST")
        pulp_manifest = list(
            csv.DictReader(manifest.decode("utf-8").splitlines(), ("name", "checksum", "size"))
        )

        self.assertEqual(len(pulp_manifest), FILE_FIXTURE_COUNT, pulp_manifest)

    def do_range_request_download_test(self):
        file_path = "1.iso"

        headers = {"Range": "bytes=0-9"}  # first 10 bytes
        NUM_BYTES = 10

        req1 = download_content_unit(
            self.cfg, self.distribution.to_dict(), file_path, headers=headers
        )
        req2 = download_content_unit(
            self.cfg, self.distribution.to_dict(), file_path, headers=headers
        )

        self.assertEqual(NUM_BYTES, len(req1))
        self.assertEqual(NUM_BYTES, len(req2))
        self.assertEqual(req1, req2)
