"""Tests that perform actions over orphan files."""
import os
import unittest
from random import choice

from pulp_smash import cli, config, utils
from pulp_smash.exceptions import CalledProcessError
from pulp_smash.pulp3.bindings import monitor_task
from pulp_smash.pulp3.utils import (
    delete_version,
    gen_repo,
    get_content,
    get_versions,
)

from pulpcore.tests.functional.api.using_plugin.constants import FILE_CONTENT_NAME
from pulpcore.client.pulpcore import ArtifactsApi
from pulpcore.client.pulpcore import OrphansApi, OrphansCleanupApi
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
    """Test whether orphan files can be cleaned up.

    An orphan artifact is an artifact that is not in any content units.
    An orphan content unit is a content unit that is not in any repository
    version.

    """

    @classmethod
    def setUpClass(cls):
        """Create class-wide variables."""
        cls.cfg = config.get_config()
        cls.api_client = ApiClient(configuration)
        cls.cli_client = cli.Client(cls.cfg)
        cls.orphans_api = OrphansApi(core_client)
        cls.storage = utils.get_pulp_setting(cls.cli_client, "DEFAULT_FILE_STORAGE")
        cls.media_root = utils.get_pulp_setting(cls.cli_client, "MEDIA_ROOT")

    def test_clean_orphan_content_unit(self):
        """Test whether orphaned content units can be cleaned up."""
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
            relative_path = artifacts_api.read(content["artifact"]).file
            artifact_path = os.path.join(self.media_root, relative_path)
            cmd = ("ls", artifact_path)
            self.cli_client.run(cmd, sudo=True)

        file_contents_api = ContentFilesApi(self.api_client)
        # Delete first repo version. The previous removed content unit will be
        # an orphan.
        delete_version(repo, get_versions(repo.to_dict())[1]["pulp_href"])
        content_units = file_contents_api.list().to_dict()["results"]
        content_units_href = [c["pulp_href"] for c in content_units]
        self.assertIn(content["pulp_href"], content_units_href)

        orphans_response = self.orphans_api.delete()
        monitor_task(orphans_response.task)

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
            cmd = ("ls", os.path.join(self.media_root, artifact.file))
            self.cli_client.run(cmd, sudo=True)

        orphans_response = self.orphans_api.delete()
        monitor_task(orphans_response.task)

        with self.assertRaises(ApiException):
            artifacts_api.read(artifact.pulp_href)

        if self.storage == "pulpcore.app.models.storage.FileSystem":
            with self.assertRaises(CalledProcessError):
                self.cli_client.run(cmd)


class OrphansCleanUpTestCase(unittest.TestCase):
    """Test the orphan cleanup endpoint.

    An orphan artifact is an artifact that is not in any content units.
    An orphan content unit is a content unit that is not in any repository
    version.

    """

    @classmethod
    def setUpClass(cls):
        """Create class-wide variables."""
        cls.cfg = config.get_config()
        cls.api_client = ApiClient(configuration)
        cls.cli_client = cli.Client(cls.cfg)
        cls.orphans_cleanup_api = OrphansCleanupApi(core_client)
        cls.storage = utils.get_pulp_setting(cls.cli_client, "DEFAULT_FILE_STORAGE")
        cls.media_root = utils.get_pulp_setting(cls.cli_client, "MEDIA_ROOT")

    def test_clean_orphan_content_unit(self):
        """Test whether orphaned content units can be cleaned up."""
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
            relative_path = artifacts_api.read(content["artifact"]).file
            artifact_path = os.path.join(self.media_root, relative_path)
            cmd = ("ls", artifact_path)
            self.cli_client.run(cmd, sudo=True)

        file_contents_api = ContentFilesApi(self.api_client)
        # Delete first repo version. The previous removed content unit will be
        # an orphan.
        delete_version(repo, get_versions(repo.to_dict())[1]["pulp_href"])
        content_units = file_contents_api.list().to_dict()["results"]
        content_units_href = [c["pulp_href"] for c in content_units]
        self.assertIn(content["pulp_href"], content_units_href)

        orphans_response = self.orphans_cleanup_api.cleanup({})
        monitor_task(orphans_response.task)

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
            cmd = ("ls", os.path.join(self.media_root, artifact.file))
            self.cli_client.run(cmd, sudo=True)

        orphans_response = self.orphans_cleanup_api.cleanup({})
        monitor_task(orphans_response.task)

        with self.assertRaises(ApiException):
            artifacts_api.read(artifact.pulp_href)

        if self.storage == "pulpcore.app.models.storage.FileSystem":
            with self.assertRaises(CalledProcessError):
                self.cli_client.run(cmd)

    def test_clean_specific_orphans(self):
        """Test whether the `content_hrefs` param removes specific orphans but not others"""
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

        # Create two orphaned content units.
        content_a = get_content(repo.to_dict())[FILE_CONTENT_NAME][0]["pulp_href"]
        content_b = get_content(repo.to_dict())[FILE_CONTENT_NAME][1]["pulp_href"]
        content_to_remove = dict(remove_content_units=[content_a, content_b])
        repo_api.modify(repo.pulp_href, content_to_remove)

        file_contents_api = ContentFilesApi(self.api_client)
        # Delete first repo version. The previous removed content unit will be an orphan.
        delete_version(repo, get_versions(repo.to_dict())[1]["pulp_href"])
        content_units = file_contents_api.list().to_dict()["results"]
        content_units_href = [c["pulp_href"] for c in content_units]
        self.assertIn(content_a, content_units_href)
        self.assertIn(content_b, content_units_href)

        content_hrefs_dict = {"content_hrefs": [content_a]}
        orphans_response = self.orphans_cleanup_api.cleanup(content_hrefs_dict)
        monitor_task(orphans_response.task)

        content_units = file_contents_api.list().to_dict()["results"]
        content_units_href = [c["pulp_href"] for c in content_units]
        self.assertNotIn(content_a, content_units_href)
        self.assertIn(content_b, content_units_href)

    def test_clean_specific_orphans_but_no_orphans_specified(self):
        """Test whether the `content_hrefs` param raises a ValidationError with [] as the value"""
        content_hrefs_dict = {"content_hrefs": []}
        self.assertRaises(ApiException, self.orphans_cleanup_api.cleanup, content_hrefs_dict)

    def test_clean_specific_orphans_but_invalid_orphan_specified(self):
        """Test whether the `content_hrefs` param raises a ValidationError with and invalid href"""
        content_hrefs_dict = {"content_hrefs": ["/not/a/valid/content/href"]}
        self.assertRaises(ApiException, self.orphans_cleanup_api.cleanup, content_hrefs_dict)
