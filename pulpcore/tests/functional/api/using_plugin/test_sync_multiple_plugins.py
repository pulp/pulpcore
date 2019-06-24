# coding=utf-8
"""Tests related to multiple plugins."""
import unittest
from unittest import SkipTest

from pulp_smash import api, config
from pulp_smash.pulp3.constants import REPO_PATH
from pulp_smash.pulp3.utils import (
    gen_remote,
    gen_repo,
    get_added_content_summary,
    get_content_summary,
    get_removed_content_summary,
    require_pulp_plugins,
    sync,
)

from pulpcore.tests.functional.api.using_plugin.constants import (
    FILE_FIXTURE_MANIFEST_URL,
    FILE_FIXTURE_SUMMARY,
    FILE_REMOTE_PATH,
    RPM_FIXTURE_SUMMARY,
    RPM_REMOTE_PATH,
    RPM_UNSIGNED_FIXTURE_URL,
)
from pulpcore.tests.functional.api.using_plugin.utils import set_up_module  # noqa


def setUpModule():
    """Conditions to skip tests.

    Skip tests if not testing Pulp 3, or if either pulpcore, pulp_file
    or pulp_rpm aren't installed.

    refer :meth:`pulpcore.tests.functional.api.using_plugin.utils.set_up_module`
    """
    set_up_module()
    require_pulp_plugins({'pulp_rpm'}, SkipTest)


class SyncMultiplePlugins(unittest.TestCase):
    """Sync repositories with the multiple plugins in the same repo."""

    @classmethod
    def setUpClass(cls):
        """Create class-wide variables."""
        cls.cfg = config.get_config()
        cls.client = api.Client(cls.cfg, api.json_handler)

    def test_mirror_sync(self):
        """Sync multiple plugin into the same repo with mirror as `True`.

        This test targets the following issue: 4448

        * `<https://pulp.plan.io/issues/4448>`_

        This test does the following:

        1. Create a repo.
        2. Create two remotes
            a. RPM remote
            b. File remote
        3. Sync the repo with RPM remote.
        4. Sync the repo with File remote with ``Mirror=True``.
        5. Verify whether the content in the latest version of the repo
           has only File content and RPM content is deleted.
        """
        # Step 1
        repo = self.client.post(REPO_PATH, gen_repo())
        self.addCleanup(self.client.delete, repo['_href'])

        # Step 2
        rpm_remote = self.client.post(
            RPM_REMOTE_PATH,
            gen_remote(url=RPM_UNSIGNED_FIXTURE_URL)
        )
        self.addCleanup(self.client.delete, rpm_remote['_href'])

        file_remote = self.client.post(
            FILE_REMOTE_PATH,
            gen_remote(url=FILE_FIXTURE_MANIFEST_URL)
        )
        self.addCleanup(self.client.delete, file_remote['_href'])

        # Step 3
        sync(self.cfg, rpm_remote, repo)
        repo = self.client.get(repo['_href'])
        self.assertIsNotNone(repo['_latest_version_href'])
        self.assertDictEqual(
            get_added_content_summary(repo),
            RPM_FIXTURE_SUMMARY
        )

        # Step 4
        sync(self.cfg, file_remote, repo, mirror=True)
        repo = self.client.get(repo['_href'])
        self.assertIsNotNone(repo['_latest_version_href'])
        self.assertDictEqual(
            get_added_content_summary(repo),
            FILE_FIXTURE_SUMMARY
        )

        # Step 5
        self.assertDictEqual(
            get_content_summary(repo),
            FILE_FIXTURE_SUMMARY
        )
        self.assertDictEqual(
            get_removed_content_summary(repo),
            RPM_FIXTURE_SUMMARY
        )
