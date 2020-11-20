# coding=utf-8
"""
Tests PulpExporter and PulpExport functionality

NOTE: assumes ALLOWED_EXPORT_PATHS setting contains "/tmp" - all tests will fail if this is not
the case.
"""
import unittest
from pulp_smash import api, cli, config
from pulp_smash.utils import uuid4
from pulp_smash.pulp3.bindings import monitor_task
from pulp_smash.pulp3.utils import (
    delete_orphans,
    gen_repo,
)

from pulpcore.tests.functional.api.using_plugin.utils import (
    gen_file_client,
    gen_file_remote,
)

from pulpcore.client.pulpcore import (
    ApiClient as CoreApiClient,
    ExportersPulpApi,
    ExportersCoreExportsApi,
)

from pulpcore.client.pulpcore.exceptions import ApiException

from pulpcore.client.pulp_file import (
    ContentFilesApi,
    RepositoriesFileApi,
    RepositoriesFileVersionsApi,
    RepositorySyncURL,
    RemotesFileApi,
)
from pulpcore.constants import TASK_STATES

NUM_REPOS = 3
MAX_EXPORTS = 3
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
        for r in range(NUM_REPOS):
            a_repo = cls.repo_api.create(gen_repo())
            # give it a remote and sync it
            body = gen_file_remote()
            remote = cls.remote_api.create(body)
            repository_sync_data = RepositorySyncURL(remote=remote.pulp_href)
            sync_response = cls.repo_api.sync(a_repo.pulp_href, repository_sync_data)
            monitor_task(sync_response.task)
            # remember it
            a_repo = cls.repo_api.read(file_file_repository_href=a_repo.pulp_href)
            repos.append(a_repo)
            remotes.append(remote)
        return repos, remotes

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
        cls.exporter_api = ExportersPulpApi(cls.core_client)
        cls.exports_api = ExportersCoreExportsApi(cls.core_client)

        (cls.repos, cls.remotes) = cls._setup_repositories()

    @classmethod
    def tearDownClass(cls):
        """Clean up after ourselves."""
        for remote in cls.remotes:
            cls.remote_api.delete(remote.pulp_href)
        for repo in cls.repos:
            cls.repo_api.delete(repo.pulp_href)
        delete_orphans(cls.cfg)

    def _delete_exporter(self, exporter):
        """
        Utility routine to delete an exporter.

        Delete even with existing last_export should now Just Work
        (as of https://pulp.plan.io/issues/6555)
        """
        cli_client = cli.Client(self.cfg)
        cmd = ("rm", "-rf", exporter.path)
        cli_client.run(cmd, sudo=True)

        self.exporter_api.delete(exporter.pulp_href)

    def _create_exporter(self, cleanup=True, use_repos=None):
        """
        Utility routine to create an exporter for the available repositories.

        If all_repos, export everything in self.repos; otherwise only export first repo
        """

        body = {
            "name": uuid4(),
            "path": "/tmp/{}/".format(uuid4()),
            "repositories": [r.pulp_href for r in self.repos],
        }
        if use_repos:
            body["repositories"] = [r.pulp_href for r in use_repos]

        exporter = self.exporter_api.create(body)
        if cleanup:
            self.addCleanup(self._delete_exporter, exporter)
        return exporter, body


class PulpExporterTestCase(BaseExporterCase):
    """Test PulpExporter CURDL methods."""

    def test_create(self):
        """Create a PulpExporter."""
        (exporter, body) = self._create_exporter()
        self.assertIsNone(exporter.last_export)
        self.assertEqual(body["name"], exporter.name)
        self.assertEqual(body["path"], exporter.path)
        self.assertEqual(len(self.repos), len(exporter.repositories))

    def test_read(self):
        """Read a created PulpExporter."""
        (exporter_created, body) = self._create_exporter()
        exporter_read = self.exporter_api.read(exporter_created.pulp_href)
        self.assertEqual(exporter_created.name, exporter_read.name)
        self.assertEqual(exporter_created.path, exporter_read.path)
        self.assertEqual(len(exporter_created.repositories), len(exporter_read.repositories))

    def test_partial_update(self):
        """Update a PulpExporter's path."""
        (exporter_created, body) = self._create_exporter()
        body = {"path": "/tmp/{}".format(uuid4())}
        self.exporter_api.partial_update(exporter_created.pulp_href, body)
        exporter_read = self.exporter_api.read(exporter_created.pulp_href)
        self.assertNotEqual(exporter_created.path, exporter_read.path)
        self.assertEqual(body["path"], exporter_read.path)

    def test_list(self):
        """Show a set of created PulpExporters."""
        starting_exporters = self.exporter_api.list().results
        for x in range(NUM_EXPORTERS):
            self._create_exporter()
        ending_exporters = self.exporter_api.list().results
        self.assertEqual(NUM_EXPORTERS, len(ending_exporters) - len(starting_exporters))

    def test_delete(self):
        """Delete a pulpExporter."""
        (exporter_created, body) = self._create_exporter(cleanup=False)
        self._delete_exporter(exporter_created)
        try:
            self.exporter_api.read(exporter_created.pulp_href)
        except ApiException as ae:
            self.assertEqual(404, ae.status)
            return
        self.fail("Found a deleted exporter!")


class PulpExportTestCase(BaseExporterCase):
    """Test PulpExport CRDL methods (Update is not allowed)."""

    def _gen_export(self, exporter, body={}):
        """Create and read back an export for the specified PulpExporter."""
        export_response = self.exports_api.create(exporter.pulp_href, body)
        monitor_task(export_response.task)
        task = self.client.get(export_response.task)
        resources = task["created_resources"]
        self.assertEqual(1, len(resources))
        reports = task["progress_reports"]
        found_artifacts = False
        found_content = False
        for r in reports:
            self.assertEqual(TASK_STATES.COMPLETED, r["state"])
            found_artifacts |= r["code"] == "export.artifacts"
            found_content |= r["code"] == "export.repo.version.content"
        self.assertTrue(found_artifacts, "No artifacts exported!")
        self.assertTrue(found_content, "No content exported!")
        export_href = resources[0]
        export = self.exports_api.read(export_href)
        self.assertIsNotNone(export)
        return export

    def test_export(self):
        """Issue and evaluate a PulpExport (tests both Create and Read)."""
        (exporter, body) = self._create_exporter(cleanup=False)
        try:
            export = self._gen_export(exporter)
            self.assertIsNotNone(export)
            self.assertEqual(len(exporter.repositories), len(export.exported_resources))
            self.assertIsNotNone(export.output_file_info)
            self.assertIsNotNone(export.toc_info)
            for an_export_filename in export.output_file_info.keys():
                self.assertFalse("//" in an_export_filename)

        finally:
            self._delete_exporter(exporter)

    def test_list(self):
        """Find all the PulpExports for a PulpExporter."""
        (exporter, body) = self._create_exporter(cleanup=False)
        try:
            export = None
            for i in range(MAX_EXPORTS):
                export = self._gen_export(exporter)
            exporter = self.exporter_api.read(exporter.pulp_href)
            self.assertEqual(exporter.last_export, export.pulp_href)
            exports = self.exports_api.list(exporter.pulp_href).results
            self.assertEqual(MAX_EXPORTS, len(exports))
        finally:
            self._delete_exporter(exporter)

    def _delete_export(self, export):
        """
        Delete a PulpExport and test that it is gone.

        :param export: PulpExport to be deleted
        :return: true if specified export is gone, false if we can still find it
        """
        self.exports_api.delete(export.pulp_href)
        try:
            self.exports_api.read(export.pulp_href)
        except ApiException as ae:
            self.assertEqual(404, ae.status)
            return True
        return False

    def test_delete(self):
        """
        Test deleting exports for a PulpExporter.

        NOTE: Attempting to delete the current last_export is forbidden.
        """
        (exporter, body) = self._create_exporter(cleanup=False)
        try:
            # Do three exports
            first_export = self._gen_export(exporter)
            self._gen_export(exporter)
            last_export = self._gen_export(exporter)

            # delete one make sure it's gone
            if not self._delete_export(first_export):
                self.fail("Failed to delete an export")

            # make sure the exporter knows it's gone
            exporter = self.exporter_api.read(exporter.pulp_href)
            exports = self.exports_api.list(exporter.pulp_href).results
            self.assertEqual(2, len(exports))

            # Now try to delete the last_export export and succeed
            # as of https://pulp.plan.io/issues/6555
            self._delete_export(last_export)
            # Make sure the exporter is still around...
            exporter = self.exporter_api.read(exporter.pulp_href)
        finally:
            self._delete_exporter(exporter)

    @unittest.skip("not yet implemented")
    def test_export_output(self):
        """Create an export and evaluate the resulting export-file."""
        self.fail("test_export_file")

    def test_export_by_version_validation(self):
        repositories = self.repos
        latest_versions = [r.latest_version_href for r in repositories]

        # exporter for one repo. specify one version
        (exporter, body) = self._create_exporter(use_repos=[repositories[0]])
        body = {"versions": [latest_versions[0]]}
        self._gen_export(exporter, body)

        # exporter for one repo. specify one *wrong* version
        with self.assertRaises(ApiException) as ae:
            (exporter, body) = self._create_exporter(use_repos=[repositories[0]])
            body = {"versions": [latest_versions[1]]}
            self._gen_export(exporter, body)
        self.assertTrue("must belong to" in ae.exception.body)

        # exporter for two repos, specify one version
        with self.assertRaises(ApiException) as ae:
            (exporter, body) = self._create_exporter(use_repos=[repositories[0], repositories[1]])
            body = {"versions": [latest_versions[0]]}
            self._gen_export(exporter, body)
        self.assertTrue("does not match the number" in ae.exception.body)

        # exporter for two repos, specify one correct and one *wrong* version
        with self.assertRaises(ApiException) as ae:
            (exporter, body) = self._create_exporter(use_repos=[repositories[0], repositories[1]])
            body = {"versions": [latest_versions[0], latest_versions[2]]}
            self._gen_export(exporter, body)
        self.assertTrue("must belong to" in ae.exception.body)

    def test_export_by_version_results(self):
        repositories = self.repos
        latest_versions = [r.latest_version_href for r in repositories]
        zeroth_versions = []
        for v in latest_versions:
            v_parts = v.split("/")
            v_parts[-2] = "0"
            zeroth_versions.append("/".join(v_parts))

        (exporter, body) = self._create_exporter(use_repos=[repositories[0]], cleanup=False)
        try:
            # export no-version, check that /1/ was exported
            export = self._gen_export(exporter)
            self.assertTrue(export.exported_resources[0].endswith("/1/"))
            # exporter-by-version, check that /0/ was exported
            body = {"versions": [zeroth_versions[0]]}
            export = self._gen_export(exporter, body)
            self.assertTrue(export.exported_resources[0].endswith("/0/"))
        finally:
            self._delete_exporter(exporter)

    def _create_repo_and_versions(self):
        # Create a new file-repo, repo-2
        a_repo = self.repo_api.create(gen_repo())
        self.addCleanup(self.client.delete, a_repo.pulp_href)
        # get a list of all the files from one of our existing repos
        file_list = self.content_api.list(repository_version=self.repos[0].latest_version_href)
        # copy files from repositories[0] into 2, one file at a time
        results = file_list.results
        for a_file in results:
            href = a_file.pulp_href
            modify_response = self.repo_api.modify(a_repo.pulp_href, {"add_content_units": [href]})
            monitor_task(modify_response.task)
        # get all versions of that repo
        # should now be 4, with 0/1/2/3 files as content
        versions = self.versions_api.list(a_repo.pulp_href, ordering="number")
        self.assertIsNotNone(versions)
        self.assertEqual(4, versions.count)
        return a_repo, versions

    def test_incremental(self):
        # create a repo with 4 repo-versions
        a_repo, versions = self._create_repo_and_versions()
        # create exporter for that repository
        (exporter, body) = self._create_exporter(use_repos=[a_repo], cleanup=False)
        try:
            # negative - ask for an incremental without having a last_export
            with self.assertRaises(ApiException):
                body = {"full": False}
                self._gen_export(exporter, body)

            # export repo-2-version[1]-full versions.results[1]
            body = {"versions": [versions.results[1].pulp_href]}
            self._gen_export(exporter, body)
            # export repo-2-version[2]
            body = {"versions": [versions.results[2].pulp_href], "full": False}
            self._gen_export(exporter, body)
            # export repo-2-latest
            body = {"full": False}
            self._gen_export(exporter, body)
        finally:
            self._delete_exporter(exporter)

    def test_chunking(self):
        a_repo = self.repo_api.create(gen_repo())
        self.addCleanup(self.client.delete, a_repo.pulp_href)
        (exporter, body) = self._create_exporter(use_repos=[a_repo], cleanup=False)
        try:
            body = {"chunk_size": "250B"}
            export = self._gen_export(exporter, body)
            info = export.output_file_info
            self.assertIsNotNone(info)
            self.assertTrue(len(info) > 1)
        finally:
            self._delete_exporter(exporter)

    def test_start_end_incrementals(self):
        # create a repo with 4 repo-versions
        a_repo, versions = self._create_repo_and_versions()
        (exporter, body) = self._create_exporter(use_repos=[a_repo], cleanup=False)
        try:
            # export from version-1 to latest last=v3
            body = {"start_versions": [versions.results[1].pulp_href], "full": False}
            self._gen_export(exporter, body)

            # export from version-1 to version-2, last=v2
            body = {
                "start_versions": [versions.results[1].pulp_href],
                "versions": [versions.results[2].pulp_href],
                "full": False,
            }
            self._gen_export(exporter, body)

            # negative attempt, start_versions= is not a version
            with self.assertRaises(ApiException):
                body = {"start_versions": [a_repo.pulp_href], "full": False}
                self._gen_export(exporter, body)

            # negative attempt, start_versions= and Full=True
            with self.assertRaises(ApiException):
                body = {"start_versions": [versions.results[2].pulp_href], "full": True}
                self._gen_export(exporter, body)

            # negative attempt, start_versions= is a version from Some Other Repo
            with self.assertRaises(ApiException):
                second_repo, second_versions = self._create_repo_and_versions()
                body = {"start_versions": [second_versions.results[0].pulp_href], "full": False}
                self._gen_export(exporter, body)
        finally:
            self._delete_exporter(exporter)
