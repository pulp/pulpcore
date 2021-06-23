import os
import unittest
from random import sample
from urllib.parse import urljoin

from pulp_smash import api, cli, config, utils
from pulp_smash.pulp3.bindings import delete_orphans
from pulp_smash.pulp3.constants import BASE_PATH
from pulp_smash.pulp3.utils import (
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

REPAIR_PATH = urljoin(BASE_PATH, "repair/")


SUPPORTED_STORAGE_FRAMEWORKS = [
    "django.core.files.storage.FileSystemStorage",
    "pulpcore.app.models.storage.FileSystem",
]


class ArtifactRepairTestCase(unittest.TestCase):
    """Test whether missing and corrupted artifact files can be redownloaded."""

    @classmethod
    def setUpClass(cls):
        """Create class-wide variables."""
        cls.cfg = config.get_config()
        cls.api_client = api.Client(cls.cfg, api.smart_handler)
        cls.cli_client = cli.Client(cls.cfg)

        storage = utils.get_pulp_setting(cls.cli_client, "DEFAULT_FILE_STORAGE")
        if storage not in SUPPORTED_STORAGE_FRAMEWORKS:
            raise unittest.SkipTest(
                "Cannot simulate bit-rot on this storage platform ({}).".format(storage),
            )

    def setUp(self):
        """Initialize Pulp with some content for our repair tests.

        1. Create and sync a repo.
        2. Select two content units from the repo, delete one artifact and corrupt another.
        """
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
        media_root = utils.get_pulp_setting(self.cli_client, "MEDIA_ROOT")
        content1, content2 = sample(get_content(repo)[FILE_CONTENT_NAME], 2)
        # Muddify one artifact on disk.
        artifact1_path = os.path.join(media_root, self.api_client.get(content1["artifact"])["file"])
        cmd1 = ("sed", "-i", "-e", r"$a bit rot", artifact1_path)
        self.cli_client.run(cmd1, sudo=True)
        # Delete another one from disk.
        artifact2_path = os.path.join(media_root, self.api_client.get(content2["artifact"])["file"])
        cmd2 = ("rm", artifact2_path)
        self.cli_client.run(cmd2, sudo=True)

        self.repo = repo

    def _verify_repair_results(self, result, missing=0, corrupted=0, repaired=0):
        """Parse the repair task output and confirm it matches expectations."""
        progress_reports = {report["code"]: report for report in result["progress_reports"]}

        corrupted_units_report = progress_reports["repair.corrupted"]
        self.assertEqual(corrupted_units_report["done"], corrupted, corrupted_units_report)

        missing_units_report = progress_reports["repair.missing"]
        self.assertEqual(missing_units_report["done"], missing, missing_units_report)

        repaired_units_report = progress_reports["repair.repaired"]
        self.assertEqual(repaired_units_report["done"], repaired, repaired_units_report)

    def test_repair_global_with_checksums(self):
        """Test whether missing and corrupted files can be redownloaded.

        Do the following:

        3. Perform Pulp repair, including checksum verification.
        4. Assert that the repair task reported two corrupted and two repaired units.
        5. Repeat the Pulp repair operation.
        6. Assert that the repair task reported no missing, corrupted or repaired units.
        """
        # STEP 3
        result = self.api_client.post(REPAIR_PATH, {"verify_checksums": True})

        # STEP 4
        self._verify_repair_results(result, missing=1, corrupted=1, repaired=2)

        # STEP 5
        result = self.api_client.post(REPAIR_PATH, {"verify_checksums": True})

        # STEP 6
        self._verify_repair_results(result)

    def test_repair_global_without_checksums(self):
        """Test whether missing files can be redownloaded.

        Do the following:

        3. Perform Pulp repair, not including checksum verification.
        4. Assert that the repair task reported one missing and one repaired unit.
        5. Repeat the Pulp repair operation.
        6. Assert that the repair task reported no missing, corrupted or repaired units.
        7. Repeat the Pulp repair operation, this time including checksum verification.
        8. Assert that the repair task reported one corrupted and one repaired unit.
        """
        # STEP 3
        result = self.api_client.post(REPAIR_PATH, {"verify_checksums": False})

        # STEP 4
        self._verify_repair_results(result, missing=1, repaired=1)

        # STEP 5
        result = self.api_client.post(REPAIR_PATH, {"verify_checksums": False})

        # STEP 6
        self._verify_repair_results(result)

        # STEP 7
        result = self.api_client.post(REPAIR_PATH, {"verify_checksums": True})

        # STEP 8
        self._verify_repair_results(result, corrupted=1, repaired=1)

    def test_repair_repository_version_with_checksums(self):
        """Test whether corrupted files can be redownloaded.

        Do the following:

        3. Repair the RepositoryVersion.
        4. Assert that the repair task reported two corrupted and two repaired units.
        5. Repeat the RepositoryVersion repair operation.
        6. Assert that the repair task reported no missing, corrupted or repaired units.
        """
        # STEP 3
        latest_version = get_versions(self.repo)[-1]["pulp_href"]
        result = self.api_client.post(latest_version + "repair/", {"verify_checksums": True})

        # STEP 4
        self._verify_repair_results(result, missing=1, corrupted=1, repaired=2)

        # STEP 5
        result = self.api_client.post(latest_version + "repair/", {"verify_checksums": True})

        # STEP 6
        self._verify_repair_results(result)

    def test_repair_repository_version_without_checksums(self):
        """Test whether missing files can be redownloaded.

        Do the following:

        3. Repair the RepositoryVersion, not including checksum verification.
        4. Assert that the repair task reported one missing and one repaired unit.
        5. Repeat the RepositoryVersion repair operation.
        6. Assert that the repair task reported no missing, corrupted or repaired units.
        7. Repeat the RepositoryVersion repair operation, this time including checksum verification
        8. Assert that the repair task reported one corrupted and one repaired unit.
        """
        # STEP 3
        latest_version = get_versions(self.repo)[-1]["pulp_href"]
        result = self.api_client.post(latest_version + "repair/", {"verify_checksums": False})

        # STEP 4
        self._verify_repair_results(result, missing=1, repaired=1)

        # STEP 5
        result = self.api_client.post(REPAIR_PATH, {"verify_checksums": False})

        # STEP 6
        self._verify_repair_results(result)

        # STEP 7
        result = self.api_client.post(latest_version + "repair/", {"verify_checksums": True})

        # STEP 8
        self._verify_repair_results(result, corrupted=1, repaired=1)
