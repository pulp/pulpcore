"""
Tests PulpImporter and PulpImport functionality

NOTE: assumes ALLOWED_EXPORT_PATHS and ALLOWED_IMPORT_PATHS settings contain "/tmp" - all tests
will fail if this is not the case.
"""
import unittest

from pulp_smash import api, cli, config
from pulp_smash.utils import uuid4
from pulp_smash.pulp3.utils import (
    delete_orphans,
    gen_repo,
)

from pulp_file.tests.functional.utils import (
    gen_file_client,
    gen_file_remote,
    monitor_task,
)
from pulpcore.tests.functional.utils import monitor_task_group

from pulpcore.client.pulpcore import (
    ApiClient as CoreApiClient,
    ExportersPulpApi,
    ExportersCoreExportsApi,
    ImportersPulpApi,
    ImportersCoreImportsApi,
)

from pulpcore.client.pulpcore.exceptions import ApiException

from pulpcore.client.pulp_file import (
    RepositoriesFileApi,
    RepositorySyncURL,
    RemotesFileApi,
)

NUM_REPOS = 2


class PulpImportTestCase(unittest.TestCase):
    """
    Base functionality for PulpImporter and PulpImport test classes
    """

    @classmethod
    def _setup_repositories(cls):
        """Create and sync a number of repositories to be exported."""
        # create and remember a set of repo
        import_repos = []
        export_repos = []
        remotes = []
        for r in range(NUM_REPOS):
            import_repo = cls.repo_api.create(gen_repo())
            export_repo = cls.repo_api.create(gen_repo())
            body = gen_file_remote()
            remote = cls.remote_api.create(body)
            repository_sync_data = RepositorySyncURL(remote=remote.pulp_href)
            sync_response = cls.repo_api.sync(export_repo.pulp_href, repository_sync_data)
            monitor_task(sync_response.task)
            # remember it
            export_repos.append(export_repo)
            import_repos.append(import_repo)
            remotes.append(remote)
        return import_repos, export_repos, remotes

    @classmethod
    def _create_exporter(cls, cleanup=True):
        body = {
            "name": uuid4(),
            "repositories": [r.pulp_href for r in cls.export_repos],
            "path": "/tmp/{}".format(uuid4()),
        }
        exporter = cls.exporter_api.create(body)
        return exporter

    @classmethod
    def _create_export(cls):
        export_response = cls.exports_api.create(cls.exporter.pulp_href, {})
        monitor_task(export_response.task)
        task = cls.client.get(export_response.task)
        resources = task["created_resources"]
        export_href = resources[0]
        export = cls.exports_api.read(export_href)
        return export

    @classmethod
    def setUpClass(cls):
        """Create class-wide variables."""
        cls.cfg = config.get_config()
        cls.client = api.Client(cls.cfg, api.json_handler)
        cls.core_client = CoreApiClient(configuration=cls.cfg.get_bindings_config())
        cls.file_client = gen_file_client()

        cls.repo_api = RepositoriesFileApi(cls.file_client)
        cls.remote_api = RemotesFileApi(cls.file_client)
        cls.exporter_api = ExportersPulpApi(cls.core_client)
        cls.exports_api = ExportersCoreExportsApi(cls.core_client)
        cls.importer_api = ImportersPulpApi(cls.core_client)
        cls.imports_api = ImportersCoreImportsApi(cls.core_client)

        (cls.import_repos, cls.export_repos, cls.remotes) = cls._setup_repositories()
        cls.exporter = cls._create_exporter()
        cls.export = cls._create_export()

    @classmethod
    def _delete_exporter(cls):
        """
        Utility routine to delete an exporter.

        Sets last_exporter to null to make it possible. Also removes the export-directory
        and all its contents.
        """
        cli_client = cli.Client(cls.cfg)
        cmd = ("rm", "-rf", cls.exporter.path)
        cli_client.run(cmd, sudo=True)

        # NOTE: you have to manually undo 'last-export' if you really really REALLY want to
        #  delete an Exporter. This is...probably correct?
        body = {"last_export": None}
        cls.exporter_api.partial_update(cls.exporter.pulp_href, body)
        cls.exporter_api.delete(cls.exporter.pulp_href)

    @classmethod
    def tearDownClass(cls):
        """Clean up."""
        for remote in cls.remotes:
            cls.remote_api.delete(remote.pulp_href)
        for repo in cls.export_repos:
            cls.repo_api.delete(repo.pulp_href)
        for repo in cls.import_repos:
            cls.repo_api.delete(repo.pulp_href)

        cls._delete_exporter()
        delete_orphans(cls.cfg)

    def test_importer_create(self):
        """Test creating an importer."""
        mapping = {}

        for idx, repo in enumerate(self.export_repos):
            mapping[repo.name] = self.import_repos[idx].name

        body = {
            "name": uuid4(),
            "repo_mapping": mapping,
        }

        importer = self.importer_api.create(body)
        self.addCleanup(self.importer_api.delete, importer.pulp_href)

        self.assertEqual(importer.name, body["name"])
        importer = self.importer_api.read(importer.pulp_href)
        self.assertEqual(importer.name, body["name"])

    def test_importer_delete(self):
        """Test deleting an importer."""
        mapping = {}

        for idx, repo in enumerate(self.export_repos):
            mapping[repo.name] = self.import_repos[idx].name

        body = {
            "name": uuid4(),
            "repo_mapping": mapping,
        }

        importer = self.importer_api.create(body)
        self.assertEqual(importer.name, body["name"])

        self.importer_api.delete(importer.pulp_href)

        with self.assertRaises(ApiException) as ae:
            self.importer_api.read(importer.pulp_href)

        self.assertEqual(404, ae.exception.status)

    def test_import(self):
        """Test an import."""
        mapping = {}

        for idx, repo in enumerate(self.export_repos):
            mapping[repo.name] = self.import_repos[idx].name

        body = {
            "name": uuid4(),
            "repo_mapping": mapping,
        }

        importer = self.importer_api.create(body)
        self.addCleanup(self.importer_api.delete, importer.pulp_href)

        filenames = list(self.export.output_file_info.keys())
        import_response = self.imports_api.create(importer.pulp_href, {"path": filenames[0]})
        monitor_task(import_response.task)
        task = self.client.get(import_response.task)
        resources = task["created_resources"]
        task_group_href = resources[1]
        task_group = monitor_task_group(task_group_href)

        self.assertEqual(len(self.import_repos), task_group.completed)
        for repo in self.import_repos:
            repo = self.repo_api.read(repo.pulp_href)
            self.assertEqual(f"{repo.pulp_href}versions/1/", repo.latest_version_href)
