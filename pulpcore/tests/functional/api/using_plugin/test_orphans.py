# coding=utf-8:
"""Tests that perform actions over orphan files."""
import os
import unittest
from django.conf import settings
from random import choice
from requests.exceptions import HTTPError

from pulp_smash import api, cli, config, utils
from pulp_smash.exceptions import CalledProcessError
from pulp_smash.pulp3.constants import ARTIFACTS_PATH, MEDIA_PATH
from pulp_smash.pulp3.utils import (
    delete_orphans,
    delete_version,
    gen_repo,
    get_content,
    get_versions,
    modify_repo,
    sync,
)

from pulpcore.tests.functional.api.using_plugin.constants import (
    FILE2_URL,
    FILE_CONTENT_NAME,
    FILE_CONTENT_PATH,
    FILE_REMOTE_PATH,
    FILE_REPO_PATH,
)
from pulpcore.tests.functional.api.using_plugin.utils import gen_file_remote
from pulpcore.tests.functional.api.using_plugin.utils import (  # noqa:F401
    set_up_module as setUpModule
)


class DeleteOrphansTestCase(unittest.TestCase):
    """Test whether orphans files can be clean up.

    An orphan artifact is an artifact that is not in any content units.
    An orphan content unit is a content unit that is not in any repository
    version.

    This test targets the following issues:

    * `Pulp #3442 <https://pulp.plan.io/issues/3442>`_
    * `Pulp Smash #914 <https://github.com/pulp/pulp-smash/issues/914>`_
    """

    @classmethod
    def setUpClass(cls):
        """Create class-wide variables."""
        cls.cfg = config.get_config()
        cls.api_client = api.Client(cls.cfg, api.json_handler)
        cls.cli_client = cli.Client(cls.cfg)

    def test_clean_orphan_content_unit(self):
        """Test whether orphan content units can be clean up.

        Do the following:

        1. Create, and sync a repo.
        2. Remove a content unit from the repo. This will create a second
           repository version, and create an orphan content unit.
        3. Assert that content unit that was removed from the repo and its
           artifact are present on disk.
        4. Delete orphans.
        5. Assert that the orphan content unit was cleaned up, and its artifact
           is not present on disk.
        """
        repo = self.api_client.post(FILE_REPO_PATH, gen_repo())
        self.addCleanup(self.api_client.delete, repo['pulp_href'])

        body = gen_file_remote()
        remote = self.api_client.post(FILE_REMOTE_PATH, body)
        self.addCleanup(self.api_client.delete, remote['pulp_href'])

        sync(self.cfg, remote, repo)
        repo = self.api_client.get(repo['pulp_href'])
        content = choice(get_content(repo)[FILE_CONTENT_NAME])

        # Create an orphan content unit.
        modify_repo(self.cfg, repo, remove_units=[content])

        if settings.DEFAULT_FILE_STORAGE == "pulpcore.app.models.storage.FileSystem":
            # Verify that the artifact is present on disk.
            artifact_path = os.path.join(MEDIA_PATH,
                                         self.api_client.get(content['artifact'])['file'])
            cmd = ('ls', artifact_path)
            self.cli_client.run(cmd, sudo=True)

        # Delete first repo version. The previous removed content unit will be
        # an orphan.
        delete_version(repo, get_versions(repo)[1]['pulp_href'])
        content_units = self.api_client.get(FILE_CONTENT_PATH)['results']
        self.assertIn(content, content_units)

        delete_orphans()
        content_units = self.api_client.get(FILE_CONTENT_PATH)['results']
        self.assertNotIn(content, content_units)

        if settings.DEFAULT_FILE_STORAGE == "pulpcore.app.models.storage.FileSystem":
            # Verify that the artifact was removed from disk.
            with self.assertRaises(CalledProcessError):
                self.cli_client.run(cmd)

    def test_clean_orphan_artifact(self):
        """Test whether orphan artifacts units can be clean up."""
        repo = self.api_client.post(FILE_REPO_PATH, gen_repo())
        self.addCleanup(self.api_client.delete, repo['pulp_href'])

        files = {'file': utils.http_get(FILE2_URL)}
        artifact = self.api_client.post(ARTIFACTS_PATH, files=files)

        if settings.DEFAULT_FILE_STORAGE == "pulpcore.app.models.storage.FileSystem":
            cmd = ('ls', os.path.join(MEDIA_PATH, artifact['file']))
            self.cli_client.run(cmd, sudo=True)

        delete_orphans()

        with self.assertRaises(HTTPError):
            self.api_client.get(artifact["pulp_href"])

        if settings.DEFAULT_FILE_STORAGE == "pulpcore.app.models.storage.FileSystem":
            with self.assertRaises(CalledProcessError):
                self.cli_client.run(cmd)
