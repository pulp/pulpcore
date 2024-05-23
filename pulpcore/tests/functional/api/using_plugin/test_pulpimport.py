"""
Tests PulpImporter and PulpImport functionality

NOTE: assumes ALLOWED_EXPORT_PATHS and ALLOWED_IMPORT_PATHS settings contain "/tmp" - all tests
will fail if this is not the case.
"""

import json
import os
import pytest
import uuid
from pathlib import Path

from pulpcore.app import settings

from pulpcore.client.pulpcore.exceptions import ApiException

from pulpcore.client.pulp_file import RepositorySyncURL

NUM_REPOS = 2


pytestmark = [
    pytest.mark.skipif(settings.DOMAIN_ENABLED, reason="Domains do not support import."),
    pytest.mark.skipif(
        "/tmp" not in settings.ALLOWED_IMPORT_PATHS,
        reason="Cannot run import-tests unless /tmp is in ALLOWED_IMPORT_PATHS ({}).".format(
            settings.ALLOWED_IMPORT_PATHS
        ),
    ),
]


@pytest.fixture
def import_export_repositories(
    file_bindings,
    file_repository_factory,
    file_remote_ssl_factory,
    basic_manifest_path,
    monitor_task,
):
    import_repos = []
    export_repos = []
    for r in range(NUM_REPOS):
        import_repo = file_repository_factory()
        export_repo = file_repository_factory()

        remote = file_remote_ssl_factory(manifest_path=basic_manifest_path, policy="immediate")
        repository_sync_data = RepositorySyncURL(remote=remote.pulp_href)
        sync_response = file_bindings.RepositoriesFileApi.sync(
            export_repo.pulp_href, repository_sync_data
        )
        monitor_task(sync_response.task)

        export_repo = file_bindings.RepositoriesFileApi.read(export_repo.pulp_href)

        export_repos.append(export_repo)
        import_repos.append(import_repo)

    return import_repos, export_repos


@pytest.fixture
def exporter(pulpcore_bindings, tmpdir, gen_object_with_cleanup, import_export_repositories):
    _, export_repos = import_export_repositories
    body = {
        "name": str(uuid.uuid4()),
        "repositories": [r.pulp_href for r in export_repos],
        "path": str(tmpdir),
    }
    exporter = gen_object_with_cleanup(pulpcore_bindings.ExportersPulpApi, body)
    return exporter


@pytest.fixture
def import_check_directory(tmp_path):
    """Creates a directory/file structure for testing import-check"""
    os.makedirs(f"{tmp_path}/noreaddir")
    os.makedirs(f"{tmp_path}/nowritedir")
    os.makedirs(f"{tmp_path}/nowritedir/notafile")

    Path(f"{tmp_path}/noreadfile").touch()
    Path(f"{tmp_path}/noreaddir/goodfile").touch()
    Path(f"{tmp_path}/nowritedir/goodfile").touch()
    Path(f"{tmp_path}/nowritedir/noreadfile").touch()

    os.chmod(f"{tmp_path}/nowritedir/noreadfile", 0o333)
    os.chmod(f"{tmp_path}/noreadfile", 0o333)
    os.chmod(f"{tmp_path}/noreaddir", 0o333)
    os.chmod(f"{tmp_path}/nowritedir", 0o555)

    yield tmp_path

    os.chmod(f"{tmp_path}/nowritedir/noreadfile", 0o644)
    os.chmod(f"{tmp_path}/noreadfile", 0o644)
    os.chmod(f"{tmp_path}/noreaddir", 0o755)
    os.chmod(f"{tmp_path}/nowritedir", 0o755)


@pytest.fixture
def importer_factory(pulpcore_bindings, gen_object_with_cleanup, import_export_repositories):
    def _importer_factory(name=None, exported_repos=None, mapping=None):
        """Create an importer."""
        _import_repos, _exported_repos = import_export_repositories
        if not name:
            name = str(uuid.uuid4())

        if not mapping:
            mapping = {}
            if not exported_repos:
                exported_repos = _exported_repos

            for idx, repo in enumerate(exported_repos):
                mapping[repo.name] = _import_repos[idx].name

        body = {
            "name": name,
            "repo_mapping": mapping,
        }

        importer = gen_object_with_cleanup(pulpcore_bindings.ImportersPulpApi, body)

        return importer

    return _importer_factory


def _find_toc(chunked_export):
    filenames = [f for f in list(chunked_export.output_file_info.keys()) if f.endswith("json")]
    return filenames[0]


def _find_path(created_export):
    filenames = [f for f in list(created_export.output_file_info.keys()) if f.endswith("tar")]
    return filenames[0]


@pytest.fixture
def perform_import(pulpcore_bindings, exporter, generate_export, monitor_task_group):
    def _perform_import(importer, export, chunked=False, body=None):
        """Perform an import with importer."""
        if body is None:
            body = {}

        if chunked:
            if "toc" not in body:
                body["toc"] = _find_toc(export)
        else:
            if "path" not in body:
                body["path"] = _find_path(export)

        import_response = pulpcore_bindings.ImportersPulpImportsApi.create(importer.pulp_href, body)
        task_group = monitor_task_group(import_response.task_group)

        return task_group

    return _perform_import


@pytest.mark.parallel
def test_importer_create(pulpcore_bindings, importer_factory):
    """Test creating an importer."""
    name = str(uuid.uuid4())
    importer = importer_factory(name)
    assert importer.name == name

    importer = pulpcore_bindings.ImportersPulpApi.read(importer.pulp_href)
    assert importer.name == name


@pytest.mark.parallel
def test_importer_delete(pulpcore_bindings, importer_factory):
    """Test deleting an importer."""
    importer = importer_factory()

    pulpcore_bindings.ImportersPulpApi.delete(importer.pulp_href)

    with pytest.raises(ApiException) as ae:
        pulpcore_bindings.ImportersPulpApi.read(importer.pulp_href)
    assert 404 == ae.value.status


@pytest.mark.parallel
def test_import(
    file_bindings,
    exporter,
    generate_export,
    importer_factory,
    import_export_repositories,
    perform_import,
):
    """Test an import."""
    import_repos, exported_repos = import_export_repositories
    importer = importer_factory()
    export = generate_export(exporter)
    task_group = perform_import(importer, export)
    assert (len(import_repos) + 1) == task_group.completed

    for report in task_group.group_progress_reports:
        if report.code == "import.repo.versions":
            assert report.done == len(import_repos)

    for repo in import_repos:
        repo = file_bindings.RepositoriesFileApi.read(repo.pulp_href)
        assert f"{repo.pulp_href}versions/1/" == repo.latest_version_href


@pytest.mark.parallel
@pytest.mark.parametrize("chunk_size", ["1KB", "5KB"])
def test_chunked_import(
    file_bindings,
    chunk_size,
    exporter,
    generate_export,
    importer_factory,
    import_export_repositories,
    perform_import,
):
    """Test an import."""
    import_repos, exported_repos = import_export_repositories
    importer = importer_factory()
    export = generate_export(exporter, body={"chunk_size": chunk_size})
    task_group = perform_import(importer, export, chunked=True)
    assert (len(import_repos) + 1) == task_group.completed

    for repo in import_repos:
        repo = file_bindings.RepositoriesFileApi.read(repo.pulp_href)
        assert f"{repo.pulp_href}versions/1/" == repo.latest_version_href


@pytest.fixture
def test_import_mapping_missing_repos(importer_factory, import_export_repositories):
    import_repos, exported_repos = import_export_repositories
    a_map = {"foo": "bar"}
    for repo in import_repos:
        a_map[repo.name] = repo.name
    a_map["blech"] = "bang"

    with pytest.raises(ApiException, match="['bar', 'bang']"):
        importer_factory(mapping=a_map)


@pytest.mark.parallel
def test_import_auto_repo_creation(
    pulpcore_bindings,
    file_bindings,
    basic_manifest_path,
    file_repository_factory,
    file_remote_ssl_factory,
    gen_object_with_cleanup,
    generate_export,
    monitor_task,
    perform_import,
    tmpdir,
):
    """Test the automatic repository creation feature where users do not ."""
    # 1. create and sync a new repository
    export_repo = file_repository_factory()

    remote = file_remote_ssl_factory(manifest_path=basic_manifest_path, policy="immediate")
    repository_sync_data = RepositorySyncURL(remote=remote.pulp_href)
    sync_response = file_bindings.RepositoriesFileApi.sync(
        export_repo.pulp_href, repository_sync_data
    )
    monitor_task(sync_response.task)

    export_repo = file_bindings.RepositoriesFileApi.read(export_repo.pulp_href)
    added_content_in_export_repo = file_bindings.ContentFilesApi.list(
        repository_version_added=export_repo.latest_version_href
    ).results

    # 2. export the synced repository
    body = {
        "name": str(uuid.uuid4()),
        "repositories": [export_repo.pulp_href],
        "path": str(tmpdir),
    }
    exporter = gen_object_with_cleanup(pulpcore_bindings.ExportersPulpApi, body)
    export = generate_export(exporter)

    # 3. delete the exported repository
    monitor_task(file_bindings.RepositoriesFileApi.delete(export_repo.pulp_href).task)
    assert len(file_bindings.RepositoriesFileApi.list(name=export_repo.name).results) == 0

    # 4. import the exported repository without creating an import repository beforehand
    importer = gen_object_with_cleanup(
        pulpcore_bindings.ImportersPulpApi, {"name": str(uuid.uuid4())}
    )
    perform_import(importer, export, body={"create_repositories": True})

    # 5. run assertions on the automatically created import repository
    repositories = file_bindings.RepositoriesFileApi.list(name=export_repo.name).results
    assert len(repositories) == 1

    imported_repo = repositories[0]
    assert f"{imported_repo.pulp_href}versions/1/" == imported_repo.latest_version_href

    added_content_in_imported_repo = file_bindings.ContentFilesApi.list(
        repository_version_added=imported_repo.latest_version_href
    ).results
    assert len(added_content_in_export_repo) == len(added_content_in_imported_repo)

    monitor_task(file_bindings.RepositoriesFileApi.delete(imported_repo.pulp_href).task)


@pytest.mark.parallel
def test_double_import(
    pulpcore_bindings,
    file_bindings,
    exporter,
    generate_export,
    importer_factory,
    import_export_repositories,
    perform_import,
):
    """Test two imports of our export."""
    import_repos, exported_repos = import_export_repositories
    export = generate_export(exporter)

    importer = importer_factory()
    perform_import(importer, export)
    perform_import(importer, export)

    imports = pulpcore_bindings.ImportersPulpImportsApi.list(importer.pulp_href).results
    assert len(imports) == 2

    for repo in import_repos:
        repo = file_bindings.RepositoriesFileApi.read(repo.pulp_href)
        # still only one version as pulp won't create a new version if nothing changed
        assert f"{repo.pulp_href}versions/1/" == repo.latest_version_href


@pytest.mark.parallel
def test_import_check_valid_path(pulpcore_bindings, exporter, generate_export):
    created_export = generate_export(exporter)
    body = {"path": _find_path(created_export)}
    result = pulpcore_bindings.ImportersPulpImportCheckApi.pulp_import_check_post(body)
    assert result.path.context == _find_path(created_export)
    assert result.path.is_valid
    assert len(result.path.messages) == 0
    assert result.toc is None
    assert result.repo_mapping is None


@pytest.mark.parallel
def test_import_check_valid_toc(pulpcore_bindings, exporter, generate_export):
    chunked_export = generate_export(exporter, body={"chunk_size": "5KB"})
    body = {"toc": _find_toc(chunked_export)}
    result = pulpcore_bindings.ImportersPulpImportCheckApi.pulp_import_check_post(body)
    assert result.toc.context == _find_toc(chunked_export)
    assert result.toc.is_valid
    assert len(result.toc.messages) == 0
    assert result.path is None
    assert result.repo_mapping is None


@pytest.mark.parallel
def test_import_check_repo_mapping(pulpcore_bindings):
    body = {"repo_mapping": json.dumps({"foo": "bar"})}
    result = pulpcore_bindings.ImportersPulpImportCheckApi.pulp_import_check_post(body)
    assert result.repo_mapping.context == json.dumps({"foo": "bar"})
    assert result.repo_mapping.is_valid
    assert len(result.repo_mapping.messages) == 0
    assert result.path is None
    assert result.toc is None

    body = {"repo_mapping": '{"foo": "bar"'}
    result = pulpcore_bindings.ImportersPulpImportCheckApi.pulp_import_check_post(body)
    assert result.repo_mapping.context == '{"foo": "bar"'
    assert not result.repo_mapping.is_valid
    assert result.repo_mapping.messages[0] == "invalid JSON"


@pytest.mark.parallel
def test_import_check_not_allowed(pulpcore_bindings):
    body = {"path": "/notinallowedimports"}
    result = pulpcore_bindings.ImportersPulpImportCheckApi.pulp_import_check_post(body)
    assert result.path.context == "/notinallowedimports"
    assert not result.path.is_valid
    assert len(result.path.messages) == 1, "Only not-allowed should be returned"
    assert result.path.messages[0] == "/ is not an allowed import path"

    body = {"toc": "/notinallowedimports"}
    result = pulpcore_bindings.ImportersPulpImportCheckApi.pulp_import_check_post(body)
    assert result.toc.context == "/notinallowedimports"
    assert not result.toc.is_valid
    assert len(result.toc.messages) == 1, "Only not-allowed should be returned"
    assert result.toc.messages[0] == "/ is not an allowed import path"


@pytest.mark.parallel
def test_import_check_no_file(pulpcore_bindings):
    body = {"path": "/tmp/idonotexist"}
    result = pulpcore_bindings.ImportersPulpImportCheckApi.pulp_import_check_post(body)
    assert result.path.context == "/tmp/idonotexist"
    assert not result.path.is_valid
    assert any("file /tmp/idonotexist does not exist" in s for s in result.path.messages)

    body = {"toc": "/tmp/idonotexist"}
    result = pulpcore_bindings.ImportersPulpImportCheckApi.pulp_import_check_post(body)
    assert result.toc.context == "/tmp/idonotexist"
    assert not result.toc.is_valid
    assert any("file /tmp/idonotexist does not exist" in s for s in result.toc.messages)


@pytest.mark.parallel
def test_import_check_all_valid(pulpcore_bindings, exporter, generate_export):
    created_export = generate_export(exporter)
    chunked_export = generate_export(exporter, body={"chunk_size": "5KB"})
    body = {
        "path": _find_path(created_export),
        "toc": _find_toc(chunked_export),
        "repo_mapping": json.dumps({"foo": "bar"}),
    }
    result = pulpcore_bindings.ImportersPulpImportCheckApi.pulp_import_check_post(body)
    assert result.path.context == _find_path(created_export)
    assert result.toc.context == _find_toc(chunked_export)
    assert result.repo_mapping.context == json.dumps({"foo": "bar"})

    assert result.path.is_valid
    assert result.toc.is_valid
    assert result.repo_mapping.is_valid

    assert len(result.path.messages) == 0
    assert len(result.toc.messages) == 0
    assert len(result.repo_mapping.messages) == 0


@pytest.mark.parallel
def test_import_check_multiple_errors(pulpcore_bindings, import_check_directory):
    body = {
        "path": "/notinallowedimports",
        "toc": f"{import_check_directory}/nowritedir/notafile",
        "repo_mapping": '{"foo": "bar"',
    }
    result = pulpcore_bindings.ImportersPulpImportCheckApi.pulp_import_check_post(body)

    assert not result.path.is_valid
    assert len(result.path.messages) == 1, "Only not-allowed should be returned"
    assert result.path.messages[0] == "/ is not an allowed import path"

    assert not result.toc.is_valid
    assert any(
        f"{import_check_directory}/nowritedir/notafile is not a file" in s
        for s in result.toc.messages
    )
    assert any(
        f"directory {import_check_directory}/nowritedir must allow pulp write-access" in s
        for s in result.toc.messages
    )

    assert not result.repo_mapping.is_valid
    assert result.repo_mapping.messages[0] == "invalid JSON"


@pytest.fixture
def generate_export(pulpcore_bindings, monitor_task):
    """Create and read back an export for the specified PulpExporter."""

    def _generate_export(exporter, body=None):
        if body is None:
            body = {}

        export_response = pulpcore_bindings.ExportersPulpExportsApi.create(exporter.pulp_href, body)
        export_href = monitor_task(export_response.task).created_resources[0]
        export = pulpcore_bindings.ExportersPulpExportsApi.read(export_href)

        return export

    return _generate_export


@pytest.fixture
def exported_version(
    pulpcore_bindings,
    file_bindings,
    importer_factory,
    gen_object_with_cleanup,
    import_export_repositories,
    generate_export,
    perform_import,
    file_repo,
    monitor_task,
    tmpdir,
):
    import_repos, export_repos = import_export_repositories

    file_list = pulpcore_bindings.ContentApi.list(
        repository_version=export_repos[0].latest_version_href
    )

    # copy files from repositories[0] into new, one file at a time
    results = file_list.results
    for a_file in results:
        href = a_file.pulp_href
        modify_response = file_bindings.RepositoriesFileApi.modify(
            file_repo.pulp_href, {"add_content_units": [href]}
        )
        monitor_task(modify_response.task)
    # get all versions of that repo
    versions = file_bindings.RepositoriesFileVersionsApi.list(
        file_repo.pulp_href, ordering=["number"]
    )

    body = {
        "name": str(uuid.uuid4()),
        "repositories": [file_repo.pulp_href],
        "path": str(tmpdir),
    }
    exporter = gen_object_with_cleanup(pulpcore_bindings.ExportersPulpApi, body)

    # export from version-0 to version-1, last=v1
    body = {
        "start_versions": [versions.results[0].pulp_href],
        "versions": [versions.results[1].pulp_href],
        "full": False,
    }
    export = generate_export(exporter, body)

    importer = importer_factory(exported_repos=[file_repo])
    task_group = perform_import(importer, export, chunked=False)

    return import_repos, task_group


@pytest.mark.parallel
def test_import_not_latest_version(exported_version, file_bindings):
    """Test an import."""
    import_repos, task_group = exported_version
    for report in task_group.group_progress_reports:
        if report.code == "import.repo.versions":
            assert report.done == 1

    imported_repo = file_bindings.RepositoriesFileApi.read(import_repos[0].pulp_href)
    assert f"{imported_repo.pulp_href}versions/0/" != imported_repo.latest_version_href
