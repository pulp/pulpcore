"""Tests that perform actions over publications."""
import unittest
from itertools import permutations

from pulp_smash import api, config
from pulp_smash.pulp3.utils import gen_distribution, gen_repo, get_content, modify_repo, sync
from requests.exceptions import HTTPError

from pulpcore.tests.functional.api.using_plugin.constants import (
    FILE_CONTENT_NAME,
    FILE_DISTRIBUTION_PATH,
    FILE_PUBLICATION_PATH,
    FILE_REMOTE_PATH,
    FILE_REPO_PATH,
)
from pulpcore.tests.functional.api.using_plugin.utils import (
    create_file_publication,
    gen_file_remote,
)
from pulpcore.tests.functional.api.using_plugin.utils import set_up_module as setUpModule  # noqa
from pulpcore.tests.functional.api.using_plugin.utils import skip_if
from pulpcore.tests.functional.api.utils import parse_date_from_string


class PublicationsTestCase(unittest.TestCase):
    """Perform actions over publications."""

    @classmethod
    def setUpClass(cls):
        """Create class-wide variables."""
        cls.cfg = config.get_config()
        cls.client = api.Client(cls.cfg, api.page_handler)
        cls.client_echo = api.Client(cls.cfg, api.echo_handler)
        cls.remote = {}
        cls.publication = {}
        cls.repo = {}
        try:
            cls.repo.update(cls.client.post(FILE_REPO_PATH, gen_repo()))
            cls.repo_initial_version = cls.repo["latest_version_href"]
            body = gen_file_remote()
            cls.remote.update(cls.client.post(FILE_REMOTE_PATH, body))
            sync(cls.cfg, cls.remote, cls.repo)
            # update to get latest_version_href
            cls.repo.update(cls.client.get(cls.repo["pulp_href"]))
        except Exception:
            cls.tearDownClass()
            raise

    @classmethod
    def tearDownClass(cls):
        """Clean class-wide variables."""
        for resource in (cls.remote, cls.repo):
            if resource:
                cls.client.delete(resource["pulp_href"])

    def test_01_create_file_publication(self):
        """Create a publication."""
        self.publication.update(create_file_publication(self.cfg, self.repo))

    @skip_if(bool, "publication", False)
    def test_02_read_publication(self):
        """Read a publication by its href."""
        publication = self.client.get(self.publication["pulp_href"])
        for key, val in self.publication.items():
            with self.subTest(key=key):
                self.assertEqual(publication[key], val)

    @skip_if(bool, "publication", False)
    def test_02_read_publication_with_specific_fields(self):
        """Read a publication by its href providing specific field list.

        Permutate field list to ensure different combinations on result.
        """
        fields = ("pulp_href", "pulp_created", "distributions")
        for field_pair in permutations(fields, 2):
            # ex: field_pair = ('pulp_href', 'pulp_created)
            with self.subTest(field_pair=field_pair):
                publication = self.client.get(
                    self.publication["pulp_href"], params={"fields": ",".join(field_pair)}
                )
                self.assertEqual(sorted(field_pair), sorted(publication.keys()))

    @skip_if(bool, "publication", False)
    def test_02_read_publication_without_specific_fields(self):
        """Read a publication by its href excluding specific fields."""
        # requests doesn't allow the use of != in parameters.
        url = "{}?exclude_fields=distributions".format(self.publication["pulp_href"])
        publication = self.client.get(url)
        self.assertNotIn("distributions", publication.keys())

    @skip_if(bool, "publication", False)
    def test_02_read_publications_filter_repo_version(self):
        """Read a publication by its repository version."""
        publications = self.client.get(
            FILE_PUBLICATION_PATH, params={"repository_version": self.repo["latest_version_href"]}
        )
        self.assertEqual(len(publications), 1, publications)
        for key, val in self.publication.items():
            with self.subTest(key=key):
                self.assertEqual(publications[0][key], val)

    @skip_if(bool, "publication", False)
    def test_02_read_publications_filter_repo_version_no_match(self):
        """Filter by repo version for which no publication exists."""
        publications = self.client.get(
            FILE_PUBLICATION_PATH, params={"repository_version": self.repo_initial_version}
        )
        self.assertFalse(publications)

    @skip_if(bool, "publication", False)
    def test_02_read_publications_filter_repo_version_invalid(self):
        """Filter by a repo version that does not exist."""
        invalid_repo_version = self.repo["versions_href"] + "123456789/"
        response = self.client_echo.get(
            FILE_PUBLICATION_PATH, params={"repository_version": invalid_repo_version}
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("not found for repositoryversion", response.text)

    @skip_if(bool, "publication", False)
    def test_02_read_publications_filter_created_time(self):
        """Read a publication by its created time."""
        publications = self.client.get(
            FILE_PUBLICATION_PATH, params={"pulp_created": self.publication["pulp_created"]}
        )
        self.assertEqual(len(publications), 1, publications)
        for key, val in self.publication.items():
            with self.subTest(key=key):
                self.assertEqual(publications[0][key], val)

    @skip_if(bool, "publication", False)
    def test_02_read_publications_filter_created_time_no_match(self):
        """Filter for created time for which no publication exists."""
        publications = self.client.get(
            FILE_PUBLICATION_PATH, params={"pulp_created": self.repo["pulp_created"]}
        )
        self.assertFalse(publications)

    @skip_if(bool, "publication", False)
    @unittest.skip("distribution filter not implemented")
    def test_02_read_publications_filter_distribution(self):
        """Read a publication by its distribution."""
        body = gen_distribution()
        body["publication"] = self.publication["pulp_href"]
        distribution = self.client.using_handler(api.task_handler).post(
            FILE_DISTRIBUTION_PATH, body
        )
        self.addCleanup(self.client.delete, distribution["pulp_href"])

        self.publication.update(self.client.get(self.publication["pulp_href"]))
        publications = self.client.get(
            FILE_PUBLICATION_PATH, params={"distributions": distribution["pulp_href"]}
        )
        self.assertEqual(len(publications), 1, publications)
        for key, val in self.publication.items():
            with self.subTest(key=key):
                self.assertEqual(publications[0][key], val)

    @skip_if(bool, "publication", False)
    def test_06_publication_create_order(self):
        """Assert that publications are ordered by created time.

        This test targets the following issues:

        * `Pulp Smash #954 <https://github.com/pulp/pulp-smash/issues/954>`_
        * `Pulp #3576 <https://pulp.plan.io/issues/3576>`_
        """
        # Create more 2 publications for the same repo
        for _ in range(2):
            create_file_publication(self.cfg, self.repo)

        # Read publications
        publications = self.client.get(FILE_PUBLICATION_PATH)
        self.assertEqual(len(publications), 3)

        # Assert publications are ordered by pulp_created field in descending order
        for i, publication in enumerate(publications[:-1]):
            self.assertGreater(
                parse_date_from_string(publication["pulp_created"]),  # Current
                parse_date_from_string(publications[i + 1]["pulp_created"]),  # Prev
            )

    @skip_if(bool, "publication", False)
    def test_07_delete(self):
        """Delete a publication."""
        self.client.delete(self.publication["pulp_href"])
        with self.assertRaises(HTTPError):
            self.client.get(self.publication["pulp_href"])


class PublicationRepositoryParametersTestCase(unittest.TestCase):
    """Explore publication creation using repository and repository version.

    This test targets the following issue:

    * `Pulp #4854 <https://pulp.plan.io/issues/4854>`_
    * `Pulp #4874 <https://pulp.plan.io/issues/4874>`_
    """

    @classmethod
    def setUpClass(cls):
        """Create class-wide variables."""
        cls.cfg = config.get_config()
        cls.client = api.Client(cls.cfg)

    def test_create_only_using_repoversion(self):
        """Create a publication only using repository version."""
        repo = self.create_sync_repo()
        for file_content in get_content(repo)[FILE_CONTENT_NAME]:
            modify_repo(self.cfg, repo, remove_units=[file_content])
        version_href = self.client.get(repo["versions_href"])[1]["pulp_href"]
        publication = create_file_publication(self.cfg, repo, version_href)
        self.addCleanup(self.client.delete, publication["pulp_href"])

        self.assertEqual(publication["repository_version"], version_href, publication)

    def test_create_repo_repoversion(self):
        """Create a publication using repository and repository version."""
        repo = self.create_sync_repo()
        version_href = self.client.get(repo["versions_href"])[0]["pulp_href"]

        with self.assertRaises(HTTPError) as ctx:
            self.client.using_handler(api.json_handler).post(
                FILE_PUBLICATION_PATH,
                {"repository_version": version_href, "repository": repo["pulp_href"]},
            )

        for key in ("repository", "repository_version", "not", "both"):
            self.assertIn(
                key,
                ctx.exception.response.json()["non_field_errors"][0].lower(),
                ctx.exception.response,
            )

    def create_sync_repo(self):
        """Create and sync a repository.

        Given the number of times to be synced.
        """
        repo = self.client.post(FILE_REPO_PATH, gen_repo())
        self.addCleanup(self.client.delete, repo["pulp_href"])

        remote = self.client.post(FILE_REMOTE_PATH, gen_file_remote())
        self.addCleanup(self.client.delete, remote["pulp_href"])

        sync(self.cfg, remote, repo)
        return self.client.get(repo["pulp_href"])
