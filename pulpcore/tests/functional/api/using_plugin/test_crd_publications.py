"""Tests that perform actions over publications."""
import unittest
from itertools import permutations

from pulp_smash import api, config
from pulp_smash.pulp3.utils import gen_repo, get_content, modify_repo, sync
from requests.exceptions import HTTPError

from pulpcore.tests.functional.api.using_plugin.constants import (
    FILE_CONTENT_NAME,
    FILE_PUBLICATION_PATH,
    FILE_REMOTE_PATH,
    FILE_REPO_PATH,
)
from pulpcore.tests.functional.api.using_plugin.utils import (
    create_file_publication,
    gen_file_remote,
)
from pulpcore.tests.functional.api.using_plugin.utils import set_up_module as setUpModule  # noqa
from pulpcore.tests.functional.api.utils import parse_date_from_string


class PublicationsTestCase(unittest.TestCase):
    """Perform actions over publications."""

    def setUp(self):
        """Create class-wide variables."""
        self.cfg = config.get_config()
        self.client = api.Client(self.cfg, api.page_handler)
        self.client_echo = api.Client(self.cfg, api.echo_handler)
        self.remote = {}
        self.publication = {}
        self.repo = {}
        try:
            self.repo.update(self.client.post(FILE_REPO_PATH, gen_repo()))
            self.repo_initial_version = self.repo["latest_version_href"]
            body = gen_file_remote()
            self.remote.update(self.client.post(FILE_REMOTE_PATH, body))
            sync(self.cfg, self.remote, self.repo)
            # update to get latest_version_href
            self.repo.update(self.client.get(self.repo["pulp_href"]))
        except Exception:
            self.tearDown()
            raise

    def tearDown(self):
        """Clean class-wide variables."""
        for resource in (self.remote, self.repo):
            if resource:
                self.client.delete(resource["pulp_href"])

    def test_workflow(self):
        self._create_file_publication()
        self._read_publication()
        self._read_publication_with_specific_fields()
        self._read_publication_without_specific_fields()
        self._read_publications_filter_repo_version()
        self._read_publications_filter_repo_version_no_match()
        self._read_publications_filter_repo_version_invalid()
        self._read_publications_filter_created_time()
        self._read_publications_filter_created_time_no_match()
        self._publication_create_order()
        self._delete()

    def _create_file_publication(self):
        """Create a publication."""
        self.publication.update(create_file_publication(self.cfg, self.repo))

    def _read_publication(self):
        """Read a publication by its href."""
        publication = self.client.get(self.publication["pulp_href"])
        for key, val in self.publication.items():
            with self.subTest(key=key):
                self.assertEqual(publication[key], val)

    def _read_publication_with_specific_fields(self):
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

    def _read_publication_without_specific_fields(self):
        """Read a publication by its href excluding specific fields."""
        # requests doesn't allow the use of != in parameters.
        url = "{}?exclude_fields=distributions".format(self.publication["pulp_href"])
        publication = self.client.get(url)
        self.assertNotIn("distributions", publication.keys())

    def _read_publications_filter_repo_version(self):
        """Read a publication by its repository version."""
        publications = self.client.get(
            FILE_PUBLICATION_PATH, params={"repository_version": self.repo["latest_version_href"]}
        )
        self.assertEqual(len(publications), 1, publications)
        for key, val in self.publication.items():
            with self.subTest(key=key):
                self.assertEqual(publications[0][key], val)

    def _read_publications_filter_repo_version_no_match(self):
        """Filter by repo version for which no publication exists."""
        publications = self.client.get(
            FILE_PUBLICATION_PATH, params={"repository_version": self.repo_initial_version}
        )
        self.assertFalse(publications)

    def _read_publications_filter_repo_version_invalid(self):
        """Filter by a repo version that does not exist."""
        invalid_repo_version = self.repo["versions_href"] + "123456789/"
        response = self.client_echo.get(
            FILE_PUBLICATION_PATH, params={"repository_version": invalid_repo_version}
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("not found for repositoryversion", response.text)

    def _read_publications_filter_created_time(self):
        """Read a publication by its created time."""
        publications = self.client.get(
            FILE_PUBLICATION_PATH, params={"pulp_created": self.publication["pulp_created"]}
        )
        self.assertEqual(len(publications), 1, publications)
        for key, val in self.publication.items():
            with self.subTest(key=key):
                self.assertEqual(publications[0][key], val)

    def _read_publications_filter_created_time_no_match(self):
        """Filter for created time for which no publication exists."""
        publications = self.client.get(
            FILE_PUBLICATION_PATH, params={"pulp_created": self.repo["pulp_created"]}
        )
        self.assertFalse(publications)

    def _publication_create_order(self):
        """Assert that publications are ordered by created time."""
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

    def _delete(self):
        """Delete a publication."""
        self.client.delete(self.publication["pulp_href"])
        with self.assertRaises(HTTPError):
            self.client.get(self.publication["pulp_href"])


class PublicationRepositoryParametersTestCase(unittest.TestCase):
    """Explore publication creation using repository and repository version."""

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
