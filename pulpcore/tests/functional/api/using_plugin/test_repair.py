# coding=utf-8:
"""Tests that perform actions over orphan files."""
import os
import unittest
from django.conf import settings
from random import sample

from pulp_smash import api, cli, config
from pulp_smash.pulp3.constants import MEDIA_PATH
from pulp_smash.pulp3.utils import (
    delete_orphans,
    gen_repo,
    get_content,
    get_versions,
    sync,
)

from pulpcore.tests.functional.api.using_plugin.constants import (
    FILE_CONTENT_NAME,
    FILE_REMOTE_PATH,
    FILE_REPO_PATH,
)
from pulpcore.tests.functional.api.using_plugin.utils import gen_file_remote
from pulpcore.tests.functional.api.using_plugin.utils import (  # noqa:F401
    set_up_module as setUpModule,
)


class RepairRepositoryVersionTestCase(unittest.TestCase):
    """Test whether corrupted files can be redownloaded.

    This test targets the repair feature of RepositoryVersions.
    """

    SUPPORTED_STORAGE_FRAMEWORKS = [
        "django.core.files.storage.FileSystemStorage",
        "pulpcore.app.models.storage.FileSystem",
    ]

    @classmethod
    def setUpClass(cls):
        """Create class-wide variables."""
        cls.cfg = config.get_config()
        cls.api_client = api.Client(cls.cfg, api.smart_handler)
        cls.cli_client = cli.Client(cls.cfg)

    def test_repair_repository_version(self):
        """Test whether corrupted files can be redownloaded.

        Do the following:

        1. Create, and sync a repo.
        2. Select a content unit from the repo and change its appearance on disk.
        3. Repair the RepositoryVersion.
        4. Assert that the repair task reported one corrupted and one repaired unit.
        5. Repair the RepositoryVersion.
        6. Assert that the repair task reported none corrupted and none repaired unit.
        """
        if settings.DEFAULT_FILE_STORAGE not in self.SUPPORTED_STORAGE_FRAMEWORKS:
            self.skipTest(
                "Cannot simulate bit-rot on this storage platform ({}).".format(
                    settings.DEFAULT_FILE_STORAGE
                ),
            )

        # STEP 1
        delete_orphans()
        repo = self.api_client.post(FILE_REPO_PATH, gen_repo())
        self.addCleanup(self.api_client.delete, repo["pulp_href"])

        body = gen_file_remote()
        remote = self.api_client.post(FILE_REMOTE_PATH, body)
        self.addCleanup(self.api_client.delete, remote["pulp_href"])

        sync(self.cfg, remote, repo)
        repo = self.api_client.get(repo["pulp_href"])

        # STEP 2
        content1, content2 = sample(get_content(repo)[FILE_CONTENT_NAME], 2)
        if settings.DEFAULT_FILE_STORAGE in self.SUPPORTED_STORAGE_FRAMEWORKS:
            # Muddify one artifact on disk.
            artifact1_path = os.path.join(
                MEDIA_PATH, self.api_client.get(content1["artifact"])["file"]
            )
            cmd1 = ("sed", "-i", "-e", r"$a bit rot", artifact1_path)
            self.cli_client.run(cmd1, sudo=True)
            # Delete another one from disk.
            artifact2_path = os.path.join(
                MEDIA_PATH, self.api_client.get(content2["artifact"])["file"]
            )
            cmd2 = ("rm", artifact2_path)
            self.cli_client.run(cmd2, sudo=True)
        else:
            self.fail("Corrupting files on this storage platform is not supported.")

        # STEP 3
        latest_version = get_versions(repo)[-1]["pulp_href"]
        result = self.api_client.post(latest_version + "repair/")

        # STEP 4
        corrupted_units_report = next(
            (
                report
                for report in result["progress_reports"]
                if report["code"] == "repair.corrupted"
            ),
            None,
        )
        self.assertEqual(corrupted_units_report["done"], 2, corrupted_units_report)
        repaired_units_report = next(
            (
                report
                for report in result["progress_reports"]
                if report["code"] == "repair.repaired"
            ),
            None,
        )
        self.assertEqual(repaired_units_report["done"], 2, repaired_units_report)

        # STEP 5
        result = self.api_client.post(latest_version + "repair/")

        # STEP 6
        corrupted_units_report = next(
            (
                report
                for report in result["progress_reports"]
                if report["code"] == "repair.corrupted"
            ),
            None,
        )
        self.assertEqual(corrupted_units_report["done"], 0, corrupted_units_report)
        repaired_units_report = next(
            (
                report
                for report in result["progress_reports"]
                if report["code"] == "repair.repaired"
            ),
            None,
        )
        self.assertEqual(repaired_units_report["done"], 0, repaired_units_report)
