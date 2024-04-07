"""
Tests FilesystemExporter and FilesystemExport functionality

NOTE: assumes ALLOWED_EXPORT_PATHS setting contains "/tmp" - all tests will fail if this is not
the case.
"""

import pytest
import uuid

from pulpcore.app import settings
from pulpcore.client.pulpcore.exceptions import ApiException

from pulpcore.client.pulp_file import RepositorySyncURL

NUM_REPOS = 1
NUM_EXPORTERS = 4

pytestmark = pytest.mark.skipif(settings.DOMAIN_ENABLED, reason="Domains do not support export.")


@pytest.fixture
def create_exporter(
    exporters_filesystem_api_client, gen_object_with_cleanup, add_to_filesystem_cleanup
):
    def _create_exporter(params=None):
        body = {
            "name": str(uuid.uuid4()),
            "path": "/tmp/{}/".format(str(uuid.uuid4())),
        }

        if params is not None:
            body.update(params)

        exporter_obj = gen_object_with_cleanup(exporters_filesystem_api_client, body)
        add_to_filesystem_cleanup(body["path"])

        return exporter_obj, body

    return _create_exporter


@pytest.mark.parallel
def test_create_exporter(create_exporter):
    """Create a FilesystemExporter."""
    exporter, body = create_exporter()
    assert body["name"] == exporter.name
    assert body["path"] == exporter.path


@pytest.mark.parallel
def test_create_exporter_with_custom_method_field(create_exporter):
    exporter, _ = create_exporter({"method": "symlink"})
    assert "symlink" == exporter.method

    with pytest.raises(ApiException) as ae:
        create_exporter({"method": "invalid"})
    assert 400 == ae.value.status


@pytest.mark.parallel
def test_read_exporter(create_exporter, exporters_filesystem_api_client):
    """Read a created FilesystemExporter."""
    exporter_created, body = create_exporter()
    exporter_read = exporters_filesystem_api_client.read(exporter_created.pulp_href)
    assert exporter_created.name == exporter_read.name
    assert exporter_created.path == exporter_read.path


@pytest.mark.parallel
def test_partial_update_exporter(create_exporter, exporters_filesystem_api_client, monitor_task):
    """Update a FilesystemExporter's path."""
    exporter_created, body = create_exporter()
    body = {"path": "/tmp/{}".format(str(uuid.uuid4()))}
    result = exporters_filesystem_api_client.partial_update(exporter_created.pulp_href, body)
    monitor_task(result.task)

    exporter_read = exporters_filesystem_api_client.read(exporter_created.pulp_href)
    assert exporter_created.path != exporter_read.path
    assert body["path"] == exporter_read.path


def test_list_exporter(create_exporter, exporters_filesystem_api_client):
    """Show a set of created FilesystemExporters."""
    starting_exporters = exporters_filesystem_api_client.list().results
    for x in range(NUM_EXPORTERS):
        create_exporter()
    ending_exporters = exporters_filesystem_api_client.list().results
    assert NUM_EXPORTERS == (len(ending_exporters) - len(starting_exporters))


@pytest.mark.parallel
def test_delete_exporter(exporters_filesystem_api_client, monitor_task):
    exporter = exporters_filesystem_api_client.create({"name": "test", "path": "/tmp/abc"})
    result = exporters_filesystem_api_client.delete(exporter.pulp_href)
    monitor_task(result.task)

    with pytest.raises(ApiException) as ae:
        exporters_filesystem_api_client.read(exporter.pulp_href)
    assert 404 == ae.value.status


@pytest.fixture
def publications(
    file_bindings,
    file_repository_factory,
    file_remote_factory,
    file_publication_api_client,
    monitor_task,
    basic_manifest_path,
):
    publications = []

    for r in range(NUM_REPOS):
        repo = file_repository_factory(autopublish=True)
        remote = file_remote_factory(manifest_path=basic_manifest_path, policy="immediate")

        repository_sync_data = RepositorySyncURL(remote=remote.pulp_href)
        sync_response = file_bindings.RepositoriesFileApi.sync(repo.pulp_href, repository_sync_data)
        monitor_task(sync_response.task)

        publication = file_publication_api_client.list(repository=repo.pulp_href).results[0]
        publications.append(publication)

    return publications


@pytest.fixture
def create_exporter_export(exporters_filesystem_exports_api_client, monitor_task):
    def _create_exporter_export(exporter, publication):
        body = {"publication": publication.pulp_href}
        export_response = exporters_filesystem_exports_api_client.create(exporter.pulp_href, body)
        created_resources = monitor_task(export_response.task).created_resources
        assert 1 == len(created_resources)

        return exporters_filesystem_exports_api_client.read(created_resources[0])

    return _create_exporter_export


@pytest.mark.parallel
def test_create_exporter_export(create_exporter, create_exporter_export, publications):
    """Issue an export for a FileSystemExporter object."""
    exporter, body = create_exporter({"method": "write"})
    export = create_exporter_export(exporter, publications[0])
    assert export is not None


@pytest.mark.parallel
def test_list_exporter_exports(
    create_exporter,
    exporters_filesystem_exports_api_client,
    exporters_filesystem_api_client,
    create_exporter_export,
    publications,
):
    """Find all FilesystemExports for a FilesystemExporter object."""
    exporter, body = create_exporter({"method": "write"})
    for i in range(NUM_REPOS):
        create_exporter_export(exporter, publications[i])
    exporter = exporters_filesystem_api_client.read(exporter.pulp_href)
    exports = exporters_filesystem_exports_api_client.list(exporter.pulp_href).results
    assert NUM_REPOS == len(exports)


@pytest.mark.parallel
def test_delete_exporter_export(
    create_exporter, exporters_filesystem_exports_api_client, create_exporter_export, publications
):
    """Test deleting exports for a FilesystemExporter object."""
    exporter, body = create_exporter({"method": "write"})
    export = create_exporter_export(exporter, publications[0])
    exporters_filesystem_exports_api_client.delete(export.pulp_href)
    with pytest.raises(ApiException) as ae:
        exporters_filesystem_exports_api_client.read(export.pulp_href)
    assert 404 == ae.value.status
