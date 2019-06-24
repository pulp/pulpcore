# coding=utf-8
"""Tests related to file plugin pagination."""
import unittest
from random import sample

from pulp_smash import api, config
from pulp_smash.pulp3.constants import REPO_PATH
from pulp_smash.pulp3.utils import gen_repo, get_versions

from pulpcore.tests.functional.api.using_plugin.constants import (
    FILE_CONTENT_PATH,
    FILE_MANY_FIXTURE_COUNT,
    FILE_MANY_FIXTURE_MANIFEST_URL,
)
from pulpcore.tests.functional.api.using_plugin.utils import populate_pulp
from pulpcore.tests.functional.api.using_plugin.utils import set_up_module as setUpModule  # noqa


class PaginationTestCase(unittest.TestCase):
    """Test file plugin pagination.

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
        repo = self.client.post(REPO_PATH, gen_repo())
        self.addCleanup(self.client.delete, repo['_href'])

        for content in contents:
            self.client.post(
                repo['_versions_href'],
                {'add_content_units': [content['_href']]}
            )

        # Verify pagination works for getting repo versions.
        repo = self.client.get(repo['_href'])
        repo_versions = get_versions(repo, {'page_size': 10})
        self.assertEqual(len(repo_versions), sample_size, repo_versions)
