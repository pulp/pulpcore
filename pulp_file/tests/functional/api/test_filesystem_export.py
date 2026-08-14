import json
import uuid

import pytest
from django.conf import settings

from pulpcore.client.pulpcore.exceptions import ApiException, BadRequestException
from pulpcore.constants import TASK_STATES

pytestmark = [
    pytest.mark.skipif(
        "/tmp" not in settings.ALLOWED_EXPORT_PATHS,
        reason="Cannot run export-tests unless /tmp is in ALLOWED_EXPORT_PATHS "
        f"({settings.ALLOWED_EXPORT_PATHS}).",
    ),
]


@pytest.fixture
def fs_exporter_factory(
    tmpdir,
    pulpcore_bindings,
    gen_object_with_cleanup,
    add_to_filesystem_cleanup,
):
    def _fs_exporter_factory(method="write", pulp_domain=None):
        name = str(uuid.uuid4())
        path = "{}/{}/".format(tmpdir, name)
        body = {
            "name": name,
            "path": path,
            "method": method,
        }
        kwargs = {}
        if pulp_domain:
            kwargs["pulp_domain"] = pulp_domain
        exporter = gen_object_with_cleanup(pulpcore_bindings.ExportersFilesystemApi, body, **kwargs)
        add_to_filesystem_cleanup(path)
        assert exporter.name == name
        assert exporter.path == path
        assert exporter.method == method
        return exporter

    return _fs_exporter_factory


@pytest.fixture
def fs_export_factory(pulpcore_bindings, monitor_task):
    def _fs_export_factory(exporter, body):
        task = monitor_task(
            pulpcore_bindings.ExportersFilesystemExportsApi.create(
                exporter.pulp_href, body or {}
            ).task
        )
        assert len(task.created_resources) == 1
        export = pulpcore_bindings.ExportersFilesystemExportsApi.read(task.created_resources[0])
        for report in task.progress_reports:
            assert report.state == TASK_STATES.COMPLETED
        return export

    return _fs_export_factory


@pytest.fixture
def pub_and_repo(
    file_repository_factory,
    file_bindings,
    gen_object_with_cleanup,
    random_artifact_factory,
    monitor_task,
):
    def _pub_and_repo(pulp_domain=None):
        random_artifact = random_artifact_factory(pulp_domain=pulp_domain)
        repository = file_repository_factory(pulp_domain=pulp_domain)
        kwargs = {}
        if pulp_domain:
            kwargs["pulp_domain"] = pulp_domain
        for i in range(2):
            monitor_task(
                file_bindings.ContentFilesApi.create(
                    artifact=random_artifact.pulp_href,
                    relative_path=f"{i}.dat",
                    repository=repository.pulp_href,
                    **kwargs,
                ).task
            )
        publish_data = file_bindings.FileFilePublication(repository=repository.pulp_href)
        publication = gen_object_with_cleanup(
            file_bindings.PublicationsFileApi, publish_data, **kwargs
        )
        return publication, repository

    return _pub_and_repo


@pytest.mark.parallel
def test_crud_fsexporter(fs_exporter_factory, pulpcore_bindings, monitor_task):
    # READ
    exporter = fs_exporter_factory()
    exporter_read = pulpcore_bindings.ExportersFilesystemApi.read(exporter.pulp_href)
    assert exporter_read.name == exporter.name
    assert exporter_read.path == exporter.path

    # UPDATE
    body = {"path": "/tmp/{}".format(str(uuid.uuid4()))}
    result = pulpcore_bindings.ExportersFilesystemApi.partial_update(exporter.pulp_href, body)
    monitor_task(result.task)
    exporter_read = pulpcore_bindings.ExportersFilesystemApi.read(exporter.pulp_href)
    assert exporter_read.path != exporter.path
    assert exporter_read.path == body["path"]

    # LIST
    exporters = pulpcore_bindings.ExportersFilesystemApi.list(name=exporter.name).results
    assert exporter.name in [e.name for e in exporters]

    # DELETE
    result = pulpcore_bindings.ExportersFilesystemApi.delete(exporter.pulp_href)
    monitor_task(result.task)
    with pytest.raises(ApiException):
        pulpcore_bindings.ExportersFilesystemApi.read(exporter.pulp_href)


@pytest.mark.parallel
def test_fsexport(pulpcore_bindings, fs_exporter_factory, fs_export_factory, pub_and_repo):
    exporter = fs_exporter_factory()
    publication, _ = pub_and_repo()
    # Test export
    body = {"publication": publication.pulp_href}
    export = fs_export_factory(exporter, body=body)

    # Test list and delete
    exports = pulpcore_bindings.ExportersPulpExportsApi.list(exporter.pulp_href).results
    assert len(exports) == 1
    pulpcore_bindings.ExportersPulpExportsApi.delete(export.pulp_href)
    exports = pulpcore_bindings.ExportersPulpExportsApi.list(exporter.pulp_href).results
    assert len(exports) == 0


@pytest.mark.parallel
def test_fsexport_by_version(
    fs_exporter_factory,
    fs_export_factory,
    pub_and_repo,
):
    publication, repository = pub_and_repo()
    latest = repository.latest_version_href
    zeroth = latest.replace("/2/", "/0/")

    # export by version
    exporter = fs_exporter_factory()
    body = {"repository_version": latest}
    fs_export_factory(exporter, body=body)

    # export by version with start_version
    exporter = fs_exporter_factory()
    body = {"repository_version": latest, "start_repository_version": zeroth}
    fs_export_factory(exporter, body=body)

    # export by publication with start_version
    exporter = fs_exporter_factory()
    body = {"publication": publication.pulp_href, "start_repository_version": zeroth}
    fs_export_factory(exporter, body=body)

    # negative: specify publication and version
    with pytest.raises(BadRequestException) as e:
        exporter = fs_exporter_factory()
        body = {"publication": publication.pulp_href, "repository_version": zeroth}
        fs_export_factory(exporter, body=body)
    assert e.value.status == 400
    assert json.loads(e.value.body) == {
        "non_field_errors": [
            "publication or repository_version must either be supplied but not both."
        ]
    }


def _filesystem_domain(pulpcore_bindings, gen_object_with_cleanup):
    body = {
        "name": str(uuid.uuid4()),
        "storage_class": "pulpcore.app.models.storage.FileSystem",
        "storage_settings": {"MEDIA_ROOT": "/var/lib/pulp/media/"},
    }
    return gen_object_with_cleanup(pulpcore_bindings.DomainsApi, body)


@pytest.mark.skipif(not settings.DOMAIN_ENABLED, reason="Domains not enabled.")
@pytest.mark.parallel
def test_fsexport_cross_domain(
    fs_exporter_factory,
    fs_export_factory,
    gen_object_with_cleanup,
    pulpcore_bindings,
    file_bindings,
    file_repository_factory,
    file_publication_factory,
    tmp_path,
    monitor_task,
):
    # Publication and versions live in source_domain; exporter lives in other_domain.
    source_domain = _filesystem_domain(pulpcore_bindings, gen_object_with_cleanup)
    other_domain = _filesystem_domain(pulpcore_bindings, gen_object_with_cleanup)

    src = tmp_path / "file.dat"
    src.write_text("x")
    content_href = file_bindings.ContentFilesApi.upload(
        relative_path="0.dat", file=str(src), pulp_domain=source_domain.name
    ).pulp_href
    repository = file_repository_factory(pulp_domain=source_domain.name)
    monitor_task(
        file_bindings.RepositoriesFileApi.modify(
            repository.pulp_href, {"add_content_units": [content_href]}
        ).task
    )
    repository = file_bindings.RepositoriesFileApi.read(repository.pulp_href)
    publication = file_publication_factory(
        repository=repository.pulp_href, pulp_domain=source_domain.name
    )
    latest = repository.latest_version_href
    zeroth = latest.rsplit("/", 2)[0] + "/0/"
    exporter = fs_exporter_factory(pulp_domain=other_domain.name)

    with pytest.raises(BadRequestException):
        fs_export_factory(exporter, body={"publication": publication.pulp_href})

    with pytest.raises(BadRequestException):
        fs_export_factory(exporter, body={"repository_version": latest})

    with pytest.raises(BadRequestException):
        fs_export_factory(
            exporter, body={"repository_version": latest, "start_repository_version": zeroth}
        )

    with pytest.raises(BadRequestException):
        fs_export_factory(
            exporter,
            body={"publication": publication.pulp_href, "start_repository_version": zeroth},
        )
