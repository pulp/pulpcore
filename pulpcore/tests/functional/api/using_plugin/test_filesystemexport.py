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
def create_exporter(pulpcore_bindings, gen_object_with_cleanup, add_to_filesystem_cleanup):
    def _create_exporter(params=None):
        body = {
            "name": str(uuid.uuid4()),
            "path": "/tmp/{}/".format(str(uuid.uuid4())),
        }

        if params is not None:
            body.update(params)

        exporter_obj = gen_object_with_cleanup(pulpcore_bindings.ExportersFilesystemApi, body)
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
def test_read_exporter(pulpcore_bindings, create_exporter):
    """Read a created FilesystemExporter."""
    exporter_created, body = create_exporter()
    exporter_read = pulpcore_bindings.ExportersFilesystemApi.read(exporter_created.pulp_href)
    assert exporter_created.name == exporter_read.name
    assert exporter_created.path == exporter_read.path


@pytest.mark.parallel
def test_partial_update_exporter(pulpcore_bindings, create_exporter, monitor_task):
    """Update a FilesystemExporter's path."""
    exporter_created, body = create_exporter()
    body = {"path": "/tmp/{}".format(str(uuid.uuid4()))}
    result = pulpcore_bindings.ExportersFilesystemApi.partial_update(
        exporter_created.pulp_href, body
    )
    monitor_task(result.task)

    exporter_read = pulpcore_bindings.ExportersFilesystemApi.read(exporter_created.pulp_href)
    assert exporter_created.path != exporter_read.path
    assert body["path"] == exporter_read.path


def test_list_exporter(pulpcore_bindings, create_exporter):
    """Show a set of created FilesystemExporters."""
    starting_exporters = pulpcore_bindings.ExportersFilesystemApi.list().results
    for x in range(NUM_EXPORTERS):
        create_exporter()
    ending_exporters = pulpcore_bindings.ExportersFilesystemApi.list().results
    assert NUM_EXPORTERS == (len(ending_exporters) - len(starting_exporters))


@pytest.mark.parallel
def test_delete_exporter(pulpcore_bindings, monitor_task):
    exporter = pulpcore_bindings.ExportersFilesystemApi.create({"name": "test", "path": "/tmp/abc"})
    result = pulpcore_bindings.ExportersFilesystemApi.delete(exporter.pulp_href)
    monitor_task(result.task)

    with pytest.raises(ApiException) as ae:
        pulpcore_bindings.ExportersFilesystemApi.read(exporter.pulp_href)
    assert 404 == ae.value.status


@pytest.fixture
def publications(
    file_bindings,
    file_repository_factory,
    file_remote_factory,
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

        publication = file_bindings.PublicationsFileApi.list(repository=repo.pulp_href).results[0]
        publications.append(publication)

    return publications


@pytest.fixture
def create_exporter_export(pulpcore_bindings, monitor_task):
    def _create_exporter_export(exporter, publication):
        body = {"publication": publication.pulp_href}
        export_response = pulpcore_bindings.ExportersFilesystemExportsApi.create(
            exporter.pulp_href, body
        )
        created_resources = monitor_task(export_response.task).created_resources
        assert 1 == len(created_resources)

        return pulpcore_bindings.ExportersFilesystemExportsApi.read(created_resources[0])

    return _create_exporter_export


@pytest.mark.parallel
def test_create_exporter_export(create_exporter, create_exporter_export, publications):
    """Issue an export for a FileSystemExporter object."""
    exporter, body = create_exporter({"method": "write"})
    export = create_exporter_export(exporter, publications[0])
    assert export is not None


@pytest.mark.parallel
def test_list_exporter_exports(
    pulpcore_bindings,
    create_exporter,
    create_exporter_export,
    publications,
):
    """Find all FilesystemExports for a FilesystemExporter object."""
    exporter, body = create_exporter({"method": "write"})
    for i in range(NUM_REPOS):
        create_exporter_export(exporter, publications[i])
    exporter = pulpcore_bindings.ExportersFilesystemApi.read(exporter.pulp_href)
    exports = pulpcore_bindings.ExportersFilesystemExportsApi.list(exporter.pulp_href).results
    assert NUM_REPOS == len(exports)


@pytest.mark.parallel
def test_delete_exporter_export(
    pulpcore_bindings, create_exporter, create_exporter_export, publications
):
    """Test deleting exports for a FilesystemExporter object."""
    exporter, body = create_exporter({"method": "write"})
    export = create_exporter_export(exporter, publications[0])
    pulpcore_bindings.ExportersFilesystemExportsApi.delete(export.pulp_href)
    with pytest.raises(ApiException) as ae:
        pulpcore_bindings.ExportersFilesystemExportsApi.read(export.pulp_href)
    assert 404 == ae.value.status
