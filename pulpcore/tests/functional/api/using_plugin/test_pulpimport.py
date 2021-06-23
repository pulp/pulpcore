"""
Tests PulpImporter and PulpImport functionality

NOTE: assumes ALLOWED_EXPORT_PATHS and ALLOWED_IMPORT_PATHS settings contain "/tmp" - all tests
will fail if this is not the case.
"""
import json
import unittest

from pulp_smash import api, cli, config
from pulp_smash.utils import uuid4, get_pulp_setting
from pulp_smash.pulp3.bindings import delete_orphans, monitor_task, monitor_task_group
from pulp_smash.pulp3.utils import (
    gen_repo,
)

from pulpcore.tests.functional.api.using_plugin.utils import (
    create_repo_and_versions,
    delete_exporter,
    gen_file_client,
    gen_file_remote,
)

from pulpcore.client.pulpcore import (
    ApiClient as CoreApiClient,
    ExportersPulpExportsApi,
    ExportersPulpApi,
    ImportersPulpImportCheckApi,
    ImportersPulpImportsApi,
    ImportersPulpApi,
)

from pulpcore.client.pulpcore.exceptions import ApiException

from pulpcore.client.pulp_file import (
    ContentFilesApi,
    RepositoriesFileApi,
    RepositoriesFileVersionsApi,
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
            export_repo = cls.repo_api.read(export_repo.pulp_href)
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
    def _create_chunked_export(cls):
        export_response = cls.exports_api.create(cls.exporter.pulp_href, {"chunk_size": "5KB"})
        monitor_task(export_response.task)
        task = cls.client.get(export_response.task)
        resources = task["created_resources"]
        export_href = resources[0]
        export = cls.exports_api.read(export_href)
        return export

    @classmethod
    def _setup_import_check_directories(cls):
        """Creates a directory/file structure for testing import-check"""
        cli_client = cli.Client(cls.cfg)
        cmd = (
            "mkdir",
            "-p",
            "/tmp/importcheck/noreaddir",
            "/tmp/importcheck/nowritedir",
            "/tmp/importcheck/nowritedir/notafile",
        )
        cli_client.run(cmd, sudo=False)

        cmd = ("touch", "/tmp/importcheck/noreadfile")
        cli_client.run(cmd, sudo=False)

        cmd = ("touch", "/tmp/importcheck/noreaddir/goodfile")
        cli_client.run(cmd, sudo=False)

        cmd = ("touch", "/tmp/importcheck/nowritedir/goodfile")
        cli_client.run(cmd, sudo=False)

        cmd = ("touch", "/tmp/importcheck/nowritedir/noreadfile")
        cli_client.run(cmd, sudo=False)

        cmd = ("chmod", "333", "/tmp/importcheck/nowritedir/noreadfile")
        cli_client.run(cmd, sudo=False)

        cmd = ("chmod", "333", "/tmp/importcheck/noreadfile")
        cli_client.run(cmd, sudo=False)

        cmd = ("chmod", "333", "/tmp/importcheck/noreaddir")
        cli_client.run(cmd, sudo=False)

        cmd = ("chmod", "555", "/tmp/importcheck/nowritedir")
        cli_client.run(cmd, sudo=False)

    @classmethod
    def setUpClass(cls):
        """Create class-wide variables."""
        cls.cfg = config.get_config()
        cls.cli_client = cli.Client(cls.cfg)
        allowed_imports = get_pulp_setting(cls.cli_client, "ALLOWED_IMPORT_PATHS")
        if not allowed_imports or "/tmp" not in allowed_imports:
            raise unittest.SkipTest(
                "Cannot run import-tests unless /tmp is in ALLOWED_IMPORT_PATHS ({}).".format(
                    allowed_imports
                ),
            )

        cls.client = api.Client(cls.cfg, api.json_handler)
        cls.core_client = CoreApiClient(configuration=cls.cfg.get_bindings_config())
        cls.file_client = gen_file_client()

        cls.repo_api = RepositoriesFileApi(cls.file_client)
        cls.remote_api = RemotesFileApi(cls.file_client)
        cls.versions_api = RepositoriesFileVersionsApi(cls.file_client)
        cls.content_api = ContentFilesApi(cls.file_client)
        cls.exporter_api = ExportersPulpApi(cls.core_client)
        cls.exports_api = ExportersPulpExportsApi(cls.core_client)
        cls.importer_api = ImportersPulpApi(cls.core_client)
        cls.imports_api = ImportersPulpImportsApi(cls.core_client)

        cls.import_check_api = ImportersPulpImportCheckApi(cls.core_client)

        (cls.import_repos, cls.export_repos, cls.remotes) = cls._setup_repositories()
        cls.exporter = cls._create_exporter()
        cls.export = cls._create_export()
        cls.chunked_export = cls._create_chunked_export()
        cls._setup_import_check_directories()

    @classmethod
    def _delete_import_check_structures(cls):
        """Deletes the directory tree used for testing import-check"""
        cli_client = cli.Client(cls.cfg)
        cmd = ("chmod", "-R", "+rwx", "/tmp/importcheck/")
        cli_client.run(cmd, sudo=False)
        cmd = ("rm", "-rf", "/tmp/importcheck")
        cli_client.run(cmd, sudo=False)

    @classmethod
    def _create_repo_and_versions(cls):
        a_repo, versions = create_repo_and_versions(
            cls.export_repos[0], cls.repo_api, cls.versions_api, cls.content_api
        )
        return a_repo, versions

    @classmethod
    def tearDownClass(cls):
        """Clean up."""
        for remote in cls.remotes:
            cls.remote_api.delete(remote.pulp_href)
        for repo in cls.export_repos:
            cls.repo_api.delete(repo.pulp_href)
        for repo in cls.import_repos:
            cls.repo_api.delete(repo.pulp_href)
        delete_exporter(cls.exporter)
        cls._delete_import_check_structures()
        delete_orphans()

    def _create_importer(self, name=None, cleanup=True, exported_repos=None):
        """Create an importer."""
        mapping = {}
        if not name:
            name = uuid4()
        if not exported_repos:
            exported_repos = self.export_repos

        for idx, repo in enumerate(exported_repos):
            mapping[repo.name] = self.import_repos[idx].name

        body = {
            "name": name,
            "repo_mapping": mapping,
        }

        importer = self.importer_api.create(body)

        if cleanup:
            self.addCleanup(self.importer_api.delete, importer.pulp_href)

        return importer

    def _find_toc(self):
        filenames = [
            f for f in list(self.chunked_export.output_file_info.keys()) if f.endswith("json")
        ]
        return filenames[0]

    def _find_path(self):
        filenames = [f for f in list(self.export.output_file_info.keys()) if f.endswith("tar.gz")]
        return filenames[0]

    def _perform_import(self, importer, chunked=False, an_export=None):
        """Perform an import with importer."""
        if not an_export:
            an_export = self.chunked_export if chunked else self.export

        if chunked:
            filenames = [f for f in list(an_export.output_file_info.keys()) if f.endswith("json")]
            import_response = self.imports_api.create(importer.pulp_href, {"toc": filenames[0]})
        else:
            filenames = [f for f in list(an_export.output_file_info.keys()) if f.endswith("tar.gz")]
            import_response = self.imports_api.create(importer.pulp_href, {"path": filenames[0]})
        monitor_task(import_response.task)
        task = self.client.get(import_response.task)
        resources = task["created_resources"]
        task_group_href = resources[1]
        task_group = monitor_task_group(task_group_href)

        return task_group

    def test_importer_create(self):
        """Test creating an importer."""
        name = uuid4()
        importer = self._create_importer(name)

        self.assertEqual(importer.name, name)
        importer = self.importer_api.read(importer.pulp_href)
        self.assertEqual(importer.name, name)

    def test_importer_delete(self):
        """Test deleting an importer."""
        importer = self._create_importer(cleanup=False)

        self.importer_api.delete(importer.pulp_href)

        with self.assertRaises(ApiException) as ae:
            self.importer_api.read(importer.pulp_href)

        self.assertEqual(404, ae.exception.status)

    def test_import(self):
        """Test an import."""
        importer = self._create_importer()
        task_group = self._perform_import(importer)
        self.assertEqual(len(self.import_repos) + 1, task_group.completed)

        for report in task_group.group_progress_reports:
            if report.code == "import.repo.versions":
                self.assertEqual(report.done, len(self.import_repos))

        for repo in self.import_repos:
            repo = self.repo_api.read(repo.pulp_href)
            self.assertEqual(f"{repo.pulp_href}versions/1/", repo.latest_version_href)

    def test_double_import(self):
        """Test two imports of our export."""
        importer = self._create_importer()
        self._perform_import(importer)
        self._perform_import(importer)

        imports = self.imports_api.list(importer.pulp_href).results
        self.assertEqual(len(imports), 2)

        for repo in self.import_repos:
            repo = self.repo_api.read(repo.pulp_href)
            # still only one version as pulp won't create a new version if nothing changed
            self.assertEqual(f"{repo.pulp_href}versions/1/", repo.latest_version_href)

    def test_chunked_import(self):
        """Test an import."""
        importer = self._create_importer()
        task_group = self._perform_import(importer, chunked=True)
        self.assertEqual(len(self.import_repos) + 1, task_group.completed)
        for repo in self.import_repos:
            repo = self.repo_api.read(repo.pulp_href)
            self.assertEqual(f"{repo.pulp_href}versions/1/", repo.latest_version_href)

    def test_import_check_valid_path(self):
        body = {"path": self._find_path()}
        result = self.import_check_api.pulp_import_check_post(body)
        self.assertEqual(result.path.context, self._find_path())
        self.assertTrue(result.path.is_valid)
        self.assertEqual(len(result.path.messages), 0)
        self.assertIsNone(result.toc)
        self.assertIsNone(result.repo_mapping)

    def test_import_check_valid_toc(self):
        body = {"toc": self._find_toc()}
        result = self.import_check_api.pulp_import_check_post(body)
        self.assertEqual(result.toc.context, self._find_toc())
        self.assertTrue(result.toc.is_valid)
        self.assertEqual(len(result.toc.messages), 0)
        self.assertIsNone(result.path)
        self.assertIsNone(result.repo_mapping)

    def test_import_check_repo_mapping(self):
        body = {"repo_mapping": json.dumps({"foo": "bar"})}
        result = self.import_check_api.pulp_import_check_post(body)
        self.assertEqual(result.repo_mapping.context, json.dumps({"foo": "bar"}))
        self.assertTrue(result.repo_mapping.is_valid)
        self.assertEqual(len(result.repo_mapping.messages), 0)
        self.assertIsNone(result.path)
        self.assertIsNone(result.toc)

        body = {"repo_mapping": '{"foo": "bar"'}
        result = self.import_check_api.pulp_import_check_post(body)
        self.assertEqual(result.repo_mapping.context, '{"foo": "bar"')
        self.assertFalse(result.repo_mapping.is_valid)
        self.assertEqual(result.repo_mapping.messages[0], "invalid JSON")

    def test_import_check_not_allowed(self):
        body = {"path": "/notinallowedimports"}
        result = self.import_check_api.pulp_import_check_post(body)
        self.assertEqual(result.path.context, "/notinallowedimports")
        self.assertFalse(result.path.is_valid)
        self.assertEqual(len(result.path.messages), 1, "Only not-allowed should be returned")
        self.assertEqual(result.path.messages[0], "/ is not an allowed import path")

        body = {"toc": "/notinallowedimports"}
        result = self.import_check_api.pulp_import_check_post(body)
        self.assertEqual(result.toc.context, "/notinallowedimports")
        self.assertFalse(result.toc.is_valid)
        self.assertEqual(len(result.toc.messages), 1, "Only not-allowed should be returned")
        self.assertEqual(result.toc.messages[0], "/ is not an allowed import path")

    def test_import_check_no_file(self):
        body = {"path": "/tmp/idonotexist"}
        result = self.import_check_api.pulp_import_check_post(body)
        self.assertEqual(result.path.context, "/tmp/idonotexist")
        self.assertFalse(result.path.is_valid)
        self.assertTrue(
            any("file /tmp/idonotexist does not exist" in s for s in result.path.messages)
        )

        body = {"toc": "/tmp/idonotexist"}
        result = self.import_check_api.pulp_import_check_post(body)
        self.assertEqual(result.toc.context, "/tmp/idonotexist")
        self.assertFalse(result.toc.is_valid)
        self.assertTrue(
            any("file /tmp/idonotexist does not exist" in s for s in result.toc.messages)
        )

    def test_import_check_all_valid(self):
        body = {
            "path": self._find_path(),
            "toc": self._find_toc(),
            "repo_mapping": json.dumps({"foo": "bar"}),
        }
        result = self.import_check_api.pulp_import_check_post(body)
        self.assertEqual(result.path.context, self._find_path())
        self.assertEqual(result.toc.context, self._find_toc())
        self.assertEqual(result.repo_mapping.context, json.dumps({"foo": "bar"}))

        self.assertTrue(result.path.is_valid)
        self.assertTrue(result.toc.is_valid)
        self.assertTrue(result.repo_mapping.is_valid)

        self.assertEqual(len(result.path.messages), 0)
        self.assertEqual(len(result.toc.messages), 0)
        self.assertEqual(len(result.repo_mapping.messages), 0)

    def test_import_check_multiple_errors(self):
        body = {
            "path": "/notinallowedimports",
            "toc": "/tmp/importcheck/nowritedir/notafile",
            "repo_mapping": '{"foo": "bar"',
        }
        result = self.import_check_api.pulp_import_check_post(body)

        self.assertFalse(result.path.is_valid)
        self.assertEqual(len(result.path.messages), 1, "Only not-allowed should be returned")
        self.assertEqual(result.path.messages[0], "/ is not an allowed import path")

        self.assertFalse(result.toc.is_valid)
        self.assertTrue(
            any(
                "/tmp/importcheck/nowritedir/notafile is not a file" in s
                for s in result.toc.messages
            )
        )
        # FAILS IN CI, passes locally
        # self.assertTrue(
        #     any(
        #         "directory /tmp/importcheck/nowritedir must allow pulp write-access" in s
        #         for s in result.toc.messages
        #     )
        # )

        self.assertFalse(result.repo_mapping.is_valid)
        self.assertEqual(result.repo_mapping.messages[0], "invalid JSON")

    def _gen_export(self, exporter, body={}):
        """Create and read back an export for the specified PulpExporter."""
        export_response = self.exports_api.create(exporter.pulp_href, body)
        monitor_task(export_response.task)
        task = self.client.get(export_response.task)
        resources = task["created_resources"]
        export_href = resources[0]
        export = self.exports_api.read(export_href)
        return export

    def _export_first_version(self, a_repo, versions):
        body = {
            "name": uuid4(),
            "repositories": [a_repo.pulp_href],
            "path": "/tmp/{}".format(uuid4()),
        }
        exporter = self.exporter_api.create(body)
        self.addCleanup(delete_exporter, exporter)
        # export from version-0 to version-1, last=v1
        body = {
            "start_versions": [versions.results[0].pulp_href],
            "versions": [versions.results[1].pulp_href],
            "full": False,
        }
        export = self._gen_export(exporter, body)
        return export

    def test_import_not_latest_version(self):
        try:
            repo, versions = self._create_repo_and_versions()

            export = self._export_first_version(repo, versions)
            """Test an import."""
            importer = self._create_importer(exported_repos=[repo])
            task_group = self._perform_import(importer, chunked=False, an_export=export)

            for report in task_group.group_progress_reports:
                if report.code == "import.repo.versions":
                    self.assertEqual(report.done, 1)

            imported_repo = self.repo_api.read(self.import_repos[0].pulp_href)
            self.assertNotEqual(
                f"{imported_repo.pulp_href}versions/0/", imported_repo.latest_version_href
            )
        finally:
            self.repo_api.delete(repo.pulp_href)
