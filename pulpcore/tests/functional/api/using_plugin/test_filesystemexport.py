"""
Tests FilesystemExporter and FilesystemExport functionality

NOTE: assumes ALLOWED_EXPORT_PATHS setting contains "/tmp" - all tests will fail if this is not
the case.
"""
import unittest
from pulp_smash import api, cli, config
from pulp_smash.utils import uuid4
from pulp_smash.pulp3.bindings import delete_orphans, monitor_task
from pulp_smash.pulp3.utils import gen_repo

from pulpcore.client.pulpcore.exceptions import ApiException

from pulpcore.client.pulpcore import (
    ApiClient as CoreApiClient,
    ExportersFilesystemApi,
    ExportersFilesystemExportsApi,
)
from pulpcore.client.pulp_file import (
    ContentFilesApi,
    FileFilePublication,
    PublicationsFileApi,
    RepositoriesFileApi,
    RepositoriesFileVersionsApi,
    RepositorySyncURL,
    RemotesFileApi,
)
from pulpcore.tests.functional.api.using_plugin.utils import (
    gen_file_client,
    gen_file_remote,
)

NUM_REPOS = 1
NUM_EXPORTERS = 4


class BaseExporterCase(unittest.TestCase):
    """
    Base functionality for Exporter and Export test classes

    The export process isn't possible without repositories having been sync'd - arranging for
    that to happen once per-class (instead of once-per-test) is the primary purpose of this parent
    class.
    """

    @classmethod
    def _setup_repositories(cls):
        """Create and sync a number of repositories to be exported."""
        # create and remember a set of repo
        repos = []
        remotes = []
        publications = []
        for r in range(NUM_REPOS):
            repo = cls.repo_api.create(gen_repo())
            remote = cls.remote_api.create(gen_file_remote())

            repository_sync_data = RepositorySyncURL(remote=remote.pulp_href)
            sync_response = cls.repo_api.sync(repo.pulp_href, repository_sync_data)
            monitor_task(sync_response.task)

            repo = cls.repo_api.read(file_file_repository_href=repo.pulp_href)
            publish_data = FileFilePublication(repository=repo.pulp_href)
            publish_response = cls.publication_api.create(publish_data)
            created_resources = monitor_task(publish_response.task).created_resources
            publication_href = created_resources[0]
            publication = cls.publication_api.read(publication_href)

            repos.append(repo)
            remotes.append(remote)
            publications.append(publication)
        return repos, remotes, publications

    @classmethod
    def setUpClass(cls):
        """Create class-wide variables."""
        cls.cfg = config.get_config()
        cls.client = api.Client(cls.cfg, api.json_handler)
        cls.core_client = CoreApiClient(configuration=cls.cfg.get_bindings_config())
        cls.file_client = gen_file_client()

        cls.content_api = ContentFilesApi(cls.file_client)
        cls.repo_api = RepositoriesFileApi(cls.file_client)
        cls.versions_api = RepositoriesFileVersionsApi(cls.file_client)
        cls.remote_api = RemotesFileApi(cls.file_client)
        cls.publication_api = PublicationsFileApi(cls.file_client)
        cls.exporter_api = ExportersFilesystemApi(cls.core_client)
        cls.exports_api = ExportersFilesystemExportsApi(cls.core_client)

        cls.repos, cls.remotes, cls.publications = cls._setup_repositories()

    @classmethod
    def tearDownClass(cls):
        """Clean up after ourselves."""
        for remote in cls.remotes:
            cls.remote_api.delete(remote.pulp_href)
        for repo in cls.repos:
            cls.repo_api.delete(repo.pulp_href)
        delete_orphans()

    def _delete_exporter(self, exporter):
        """
        Utility routine to delete an exporter.
        """
        cli_client = cli.Client(self.cfg)
        cmd = ("rm", "-rf", exporter.path)
        cli_client.run(cmd, sudo=True)

        result = self.exporter_api.delete(exporter.pulp_href)
        monitor_task(result.task)

    def _create_exporter(self, params={}):
        """
        Utility routine to create an exporter for the available repositories.
        """
        body = {
            "name": uuid4(),
            "path": "/tmp/{}/".format(uuid4()),
        }
        body.update(params)

        exporter = self.exporter_api.create(body)
        self.addCleanup(self._delete_exporter, exporter)
        return exporter, body


class FilesystemExporterTestCase(BaseExporterCase):
    """Test FilesystemExporter CURDL methods."""

    def test_create(self):
        """Create a FilesystemExporter."""
        exporter, body = self._create_exporter()
        self.assertEqual(body["name"], exporter.name)
        self.assertEqual(body["path"], exporter.path)

    def test_read(self):
        """Read a created FilesystemExporter."""
        exporter_created, body = self._create_exporter()
        exporter_read = self.exporter_api.read(exporter_created.pulp_href)
        self.assertEqual(exporter_created.name, exporter_read.name)
        self.assertEqual(exporter_created.path, exporter_read.path)

    def test_partial_update(self):
        """Update a FilesystemExporter's path."""
        exporter_created, body = self._create_exporter()
        body = {"path": "/tmp/{}".format(uuid4())}
        result = self.exporter_api.partial_update(exporter_created.pulp_href, body)
        monitor_task(result.task)
        exporter_read = self.exporter_api.read(exporter_created.pulp_href)
        self.assertNotEqual(exporter_created.path, exporter_read.path)
        self.assertEqual(body["path"], exporter_read.path)

    def test_list(self):
        """Show a set of created FilesystemExporters."""
        starting_exporters = self.exporter_api.list().results
        for x in range(NUM_EXPORTERS):
            self._create_exporter()
        ending_exporters = self.exporter_api.list().results
        self.assertEqual(NUM_EXPORTERS, len(ending_exporters) - len(starting_exporters))

    def test_delete(self):
        """Delete a pulpExporter."""
        exporter = self.exporter_api.create({"name": "test", "path": "/tmp/abc"})
        result = self.exporter_api.delete(exporter.pulp_href)
        monitor_task(result.task)
        with self.assertRaises(ApiException) as ae:
            self.exporter_api.read(exporter.pulp_href)
        self.assertEqual(404, ae.exception.status)

    def test_method(self):
        """Test the method field."""
        exporter, _ = self._create_exporter({"method": "symlink"})
        self.assertEqual("symlink", exporter.method)

        with self.assertRaises(ApiException) as ae:
            exporter = self._create_exporter({"method": "invalid"})
        self.assertEqual(400, ae.exception.status)


class FilesystemExportTestCase(BaseExporterCase):
    """Test FilesystemExport CRDL methods (Update is not allowed)."""

    def _gen_export(self, exporter, publication):
        """Create and read back an export for the specified FilesystemExporter."""
        body = {"publication": publication.pulp_href}
        export_response = self.exports_api.create(exporter.pulp_href, body)
        monitor_task(export_response.task)

        task = self.client.get(export_response.task)
        resources = task["created_resources"]
        self.assertEqual(1, len(resources))

        return self.exports_api.read(resources[0])

    def test_export(self):
        """Issue and evaluate a FilesystemExport (tests both Create and Read)."""
        exporter, body = self._create_exporter({"method": "write"})
        export = self._gen_export(exporter, self.publications[0])
        self.assertIsNotNone(export)

    def test_list(self):
        """Find all the FilesystemExports for a FilesystemExporter."""
        exporter, body = self._create_exporter({"method": "write"})
        for i in range(NUM_REPOS):
            self._gen_export(exporter, self.publications[i])
        exporter = self.exporter_api.read(exporter.pulp_href)
        exports = self.exports_api.list(exporter.pulp_href).results
        self.assertEqual(NUM_REPOS, len(exports))

    def test_delete(self):
        """Test deleting exports for a FilesystemExporter."""
        exporter, body = self._create_exporter({"method": "write"})
        export = self._gen_export(exporter, self.publications[0])
        self.exports_api.delete(export.pulp_href)
        with self.assertRaises(ApiException) as ae:
            self.exports_api.read(export.pulp_href)
        self.assertEqual(404, ae.exception.status)
