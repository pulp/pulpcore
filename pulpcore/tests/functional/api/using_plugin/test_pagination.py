"""Tests related to pagination."""
import unittest
from random import randint, sample

from pulp_smash import api, config
from pulp_smash.pulp3.bindings import monitor_task
from pulp_smash.pulp3.utils import gen_repo, get_versions, modify_repo

from pulpcore.tests.functional.api.using_plugin.constants import (
    FILE_CONTENT_PATH,
    FILE_MANY_FIXTURE_COUNT,
    FILE_MANY_FIXTURE_MANIFEST_URL,
    FILE_REPO_PATH,
)
from pulpcore.tests.functional.api.using_plugin.utils import populate_pulp
from pulpcore.tests.functional.api.using_plugin.utils import set_up_module as setUpModule  # noqa


class RepoVersionPaginationTestCase(unittest.TestCase):
    """Test pagination of the core RepositoryVersion endpoints.

    This test case assumes that Pulp returns 100 elements in each page of
    results. This is configurable, but the current default set by all known
    Pulp installers.
    """

    @classmethod
    def setUpClass(cls):
        """Create class-wide variables."""
        cls.cfg = config.get_config()
        cls.client = api.Client(cls.cfg, api.page_handler)

    def test_file_content(self):
        """Test pagination for repository versions."""
        # Add content to Pulp, create a repo, and add content to repo. We
        # sample 21 contents, because with page_size set to 10, this produces 3
        # pages, where the three three pages have unique combinations of values
        # for the "previous" and "next" links.
        populate_pulp(self.cfg, url=FILE_MANY_FIXTURE_MANIFEST_URL)
        sample_size = min(FILE_MANY_FIXTURE_COUNT, 21)
        contents = sample(self.client.get(FILE_CONTENT_PATH), sample_size)
        repo = self.client.post(FILE_REPO_PATH, gen_repo())
        self.addCleanup(self.client.delete, repo["pulp_href"])

        for content in contents:
            modify_repo(self.cfg, repo, add_units=[content])

        # Verify pagination works for getting repo versions.
        repo = self.client.get(repo["pulp_href"])
        repo_versions = get_versions(repo, {"page_size": 10})
        self.assertEqual(len(repo_versions), sample_size + 1, repo_versions)


class PaginationTestCase(unittest.TestCase):
    """Test pagination assuming that Pulp returns 100 elements in each page of results."""

    @classmethod
    def setUpClass(cls):
        """Create class-wide variables."""
        cls.cfg = config.get_config()
        cls.client = api.Client(cls.cfg, api.json_handler)

    def setUp(self):
        self.repos = []
        self.number_to_create = 21

        # Perform a sanity check.
        repos = self.client.using_handler(api.page_handler).get(FILE_REPO_PATH)
        assert len(repos) == 0, repos  # AssertEqual not available here yet

        # Create repos
        for _ in range(self.number_to_create):
            repo = self.client.post(FILE_REPO_PATH, gen_repo())
            self.repos.append(repo)

    def tearDown(self):
        responses = []
        for repo in self.repos:
            responses.append(self.client.delete(repo["pulp_href"]))
        for response in responses:
            monitor_task(response["task"])

    def test_pagination_workflow(self):
        self._raw_pagination()
        self._page_handler_pagination()

    def _raw_pagination(self):
        """Assert content can be paginated page by page.

        Do the following:

        1. Without using page_handler request content
        2. Save collected_results and assert it is equal the per_page param
        3. Assert there is a next link but not a previous link
        4. Loop pages "number_to_create / per_page" (3)
        5. For each page request next link and assert length equals per_page
        6. For each page assert the presence of next and previous links
        7. Assert last page is reached
        8. Assert the final count equals number_to_create
        """

        per_page = 7  # will result in 3 pages
        resp = self.client.get(FILE_REPO_PATH, params={"limit": per_page})
        collected_results = resp["results"]
        # First call returns 7 results
        self.assertEqual(len(collected_results), per_page, collected_results)
        # no previous but there is a next
        self.assertIsNone(resp["previous"], resp["previous"])
        self.assertIsNotNone(resp["next"], resp["next"])

        # paginate pages 2 and 3
        for page in range(int(self.number_to_create / per_page)):  # [0, 1, 2]
            if page == 1:
                # there is a previous and a next
                self.assertIsNotNone(resp["previous"], resp["previous"])
                self.assertIsNotNone(resp["next"], resp["next"])
                # must have twice the size
                self.assertEqual(len(collected_results), per_page * 2, collected_results)
            if page == 2:
                # last page there is no next but there is a previous
                self.assertIsNone(resp["next"], resp["next"])
                self.assertIsNotNone(resp["previous"], resp["previous"])
                # must have 3 x the size
                self.assertEqual(len(collected_results), per_page * 3, collected_results)
                break  # last page reached
            resp = self.client.get(resp["next"])
            page_results = resp["results"]
            self.assertEqual(len(page_results), per_page, page_results)
            collected_results.extend(page_results)

        # Assert the final count
        self.assertEqual(len(collected_results), self.number_to_create, collected_results)

    def _page_handler_pagination(self):
        """
        Assert page handler returns all items independent of page_size.

        This test asserts that pulp-smash page_handler will collect results from all pages and
        return it in the same call independent of the page_size provided.
        """
        repos = self.client.using_handler(api.page_handler).get(
            FILE_REPO_PATH, params={"page_size": randint(2, 11)}
        )
        self.assertEqual(len(repos), self.number_to_create, repos)
