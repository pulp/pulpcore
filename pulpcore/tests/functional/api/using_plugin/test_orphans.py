# coding=utf-8:
"""Tests that perform actions over orphan files."""
import os
import unittest
from random import choice

from pulp_smash import cli, config, utils
from pulp_smash.exceptions import CalledProcessError
from pulp_smash.pulp3.bindings import monitor_task
from pulp_smash.pulp3.constants import MEDIA_PATH
from pulp_smash.pulp3.utils import (
    delete_orphans,
    delete_version,
    gen_repo,
    get_content,
    get_versions,
)

from pulpcore.tests.functional.api.using_plugin.constants import FILE_CONTENT_NAME
from pulpcore.client.pulpcore import ArtifactsApi
from pulpcore.client.pulpcore.exceptions import ApiException
from pulpcore.client.pulp_file import (
    ApiClient,
    ContentFilesApi,
    RepositoriesFileApi,
    RepositorySyncURL,
    RemotesFileApi,
)
from pulpcore.tests.functional.utils import configuration, core_client
from pulpcore.tests.functional.api.using_plugin.utils import gen_file_remote
from pulpcore.tests.functional.api.using_plugin.utils import (  # noqa:F401
    set_up_module as setUpModule,
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
        cls.api_client = ApiClient(configuration)
        cls.cli_client = cli.Client(cls.cfg)
        cls.storage = utils.get_pulp_setting(cls.cli_client, "DEFAULT_FILE_STORAGE")

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
        repo_api = RepositoriesFileApi(self.api_client)
        remote_api = RemotesFileApi(self.api_client)

        repo = repo_api.create(gen_repo())
        self.addCleanup(repo_api.delete, repo.pulp_href)

        body = gen_file_remote()
        remote = remote_api.create(body)
        self.addCleanup(remote_api.delete, remote.pulp_href)

        # Sync the repository.
        self.assertEqual(repo.latest_version_href, f"{repo.pulp_href}versions/0/")
        repository_sync_data = RepositorySyncURL(remote=remote.pulp_href)
        sync_response = repo_api.sync(repo.pulp_href, repository_sync_data)
        monitor_task(sync_response.task)
        repo = repo_api.read(repo.pulp_href)
        content = choice(get_content(repo.to_dict())[FILE_CONTENT_NAME])

        # Create an orphan content unit.
        repo_api.modify(repo.pulp_href, dict(remove_content_units=[content["pulp_href"]]))

        artifacts_api = ArtifactsApi(core_client)

        if self.storage == "pulpcore.app.models.storage.FileSystem":
            # Verify that the artifact is present on disk.
            artifact_path = os.path.join(MEDIA_PATH, artifacts_api.read(content["artifact"]).file)
            cmd = ("ls", artifact_path)
            self.cli_client.run(cmd, sudo=True)

        file_contents_api = ContentFilesApi(self.api_client)
        # Delete first repo version. The previous removed content unit will be
        # an orphan.
        delete_version(repo, get_versions(repo.to_dict())[1]["pulp_href"])
        content_units = file_contents_api.list().to_dict()["results"]
        content_units_href = [c["pulp_href"] for c in content_units]
        self.assertIn(content["pulp_href"], content_units_href)

        delete_orphans()
        content_units = file_contents_api.list().to_dict()["results"]
        content_units_href = [c["pulp_href"] for c in content_units]
        self.assertNotIn(content["pulp_href"], content_units_href)

        if self.storage == "pulpcore.app.models.storage.FileSystem":
            # Verify that the artifact was removed from disk.
            with self.assertRaises(CalledProcessError):
                self.cli_client.run(cmd)

    def test_clean_orphan_artifact(self):
        """Test whether orphan artifacts units can be clean up."""
        repo_api = RepositoriesFileApi(self.api_client)
        repo = repo_api.create(gen_repo())
        self.addCleanup(repo_api.delete, repo.pulp_href)

        artifacts_api = ArtifactsApi(core_client)
        artifact = artifacts_api.create(file=__file__)

        if self.storage == "pulpcore.app.models.storage.FileSystem":
            cmd = ("ls", os.path.join(MEDIA_PATH, artifact.file))
            self.cli_client.run(cmd, sudo=True)

        delete_orphans()

        with self.assertRaises(ApiException):
            artifacts_api.read(artifact.pulp_href)

        if self.storage == "pulpcore.app.models.storage.FileSystem":
            with self.assertRaises(CalledProcessError):
                self.cli_client.run(cmd)
