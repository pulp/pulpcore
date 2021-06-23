"""Tests related to content path."""
import unittest

from pulp_smash import api, config
from pulp_smash.pulp3.bindings import delete_orphans
from pulp_smash.pulp3.utils import gen_remote, gen_repo, sync

from pulpcore.tests.functional.api.using_plugin.constants import (
    FILE_FIXTURE_MANIFEST_URL,
    FILE_REMOTE_PATH,
    FILE_REPO_PATH,
)
from pulpcore.tests.functional.api.using_plugin.utils import create_file_publication
from pulpcore.tests.functional.api.using_plugin.utils import (  # noqa:F401
    set_up_module as setUpModule,
)


class SyncPublishContentPathTestCase(unittest.TestCase):
    """Test whether sync/publish for content already in Pulp.

    Different code paths are used in Pulp for the cases when artifacts are
    already present on the filesystem during sync and when they are not
    downloaded yet

    This test targets the following issue:

    `Pulp #4442 <https://pulp.plan.io/issues/4442>`_

    Does the following:

    1. Assure that no content from repository A is downloaded.
    2. Sync/publish repository A with download policy immediate.
    3. Sync/publish repository A again with download policy immediate.
    4. No failure in 2 shows that sync went fine when content was
       not present on the disk and in the database.
    5. No failure in 3 shows that sync went fine when content was already
       present on the disk and in the database.

    """

    def test_all(self):
        """Test whether sync/publish for content already in Pulp."""
        cfg = config.get_config()
        client = api.Client(cfg, api.page_handler)

        # step 1. delete orphans to assure that no content is present on disk,
        # or database.
        delete_orphans()

        remote = client.post(FILE_REMOTE_PATH, gen_remote(FILE_FIXTURE_MANIFEST_URL))
        self.addCleanup(client.delete, remote["pulp_href"])

        repo = client.post(FILE_REPO_PATH, gen_repo())
        self.addCleanup(client.delete, repo["pulp_href"])

        for _ in range(2):
            sync(cfg, remote, repo)
            repo = client.get(repo["pulp_href"])
            create_file_publication(cfg, repo)
