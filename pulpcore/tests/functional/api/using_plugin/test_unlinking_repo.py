"""Tests that perform action over remotes"""

import unittest

from pulp_smash import api, config
from pulp_smash.pulp3.utils import gen_repo, get_content, sync

from pulpcore.tests.functional.api.using_plugin.constants import (
    FILE_CONTENT_NAME,
    FILE_REMOTE_PATH,
    FILE_REPO_PATH,
)
from pulpcore.tests.functional.api.using_plugin.utils import gen_file_remote
from pulpcore.tests.functional.api.using_plugin.utils import set_up_module as setUpModule  # noqa


class RemotesTestCase(unittest.TestCase):
    """Verify remotes can be used with different repos."""

    def test_all(self):
        """Verify remotes can be used with different repos.

        This test explores the design choice stated in `Pulp #3341`_ that
        remove the FK from remotes to repository.
        Allowing remotes to be used with different
        repositories.

        .. _Pulp #3341: https://pulp.plan.io/issues/3341

        Do the following:

        1. Create a remote.
        2. Create 2 repositories.
        3. Sync both repositories using the same remote.
        4. Assert that the two repositories have the same contents.
        """
        cfg = config.get_config()

        # Create a remote.
        client = api.Client(cfg, api.json_handler)
        body = gen_file_remote()
        remote = client.post(FILE_REMOTE_PATH, body)
        self.addCleanup(client.delete, remote["pulp_href"])

        # Create and sync repos.
        repos = []
        for _ in range(2):
            repo = client.post(FILE_REPO_PATH, gen_repo())
            self.addCleanup(client.delete, repo["pulp_href"])
            sync(cfg, remote, repo)
            repos.append(client.get(repo["pulp_href"]))

        # Compare contents of repositories.
        contents = []
        for repo in repos:
            contents.append(get_content(repo)[FILE_CONTENT_NAME])
        self.assertEqual(
            {content["pulp_href"] for content in contents[0]},
            {content["pulp_href"] for content in contents[1]},
        )
