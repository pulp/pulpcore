import json
import pytest
import uuid

from pulpcore.client.pulpcore.exceptions import ApiException
from pulpcore.client.pulpcore.exceptions import BadRequestException
from pulpcore.app import settings
from pulpcore.constants import TASK_STATES


pytestmark = [
    pytest.mark.skipif(
        "/tmp" not in settings.ALLOWED_EXPORT_PATHS,
        reason="Cannot run export-tests unless /tmp is in ALLOWED_EXPORT_PATHS "
        f"({settings.ALLOWED_EXPORT_PATHS}).",
    ),
]


@pytest.fixture
def pulp_exporter_factory(
    tmpdir,
    pulpcore_bindings,
    gen_object_with_cleanup,
    add_to_filesystem_cleanup,
):
    def _pulp_exporter_factory(
        repositories=None,
        pulp_domain=None,
    ):
        if repositories is None:
            repositories = []
        name = str(uuid.uuid4())
        path = "{}/{}/".format(tmpdir, name)
        body = {
            "name": name,
            "path": path,
            "repositories": [r.pulp_href for r in repositories],
        }
        kwargs = {}
        if pulp_domain:
            kwargs["pulp_domain"] = pulp_domain.name

        exporter = gen_object_with_cleanup(pulpcore_bindings.ExportersPulpApi, body, **kwargs)
        add_to_filesystem_cleanup(path)
        assert exporter.name == name
        assert exporter.path == path
        assert len(exporter.repositories) == len(repositories)
        assert exporter.last_export is None
        return exporter

    return _pulp_exporter_factory


@pytest.fixture
def pulp_export_factory(pulpcore_bindings, monitor_task):
    def _pulp_export_factory(exporter, body=None):
        task = monitor_task(
            pulpcore_bindings.ExportersPulpExportsApi.create(exporter.pulp_href, body or {}).task
        )
        assert len(task.created_resources) == 1
        shared_resources = [
            r
            for r in task.reserved_resources_record
            if r.startswith("shared:") and "file.filerepository" in r
        ]
        assert len(exporter.repositories) == len(shared_resources)

        export = pulpcore_bindings.ExportersPulpExportsApi.read(task.created_resources[0])
        for report in task.progress_reports:
            assert report.state == TASK_STATES.COMPLETED
        report_codes = [report.code for report in task.progress_reports]
        assert "export.artifacts" in report_codes
        assert "export.repo.version.content" in report_codes
        assert len(export.exported_resources) == len(exporter.repositories)
        assert export.output_file_info is not None
        assert export.toc_info is not None
        for export_filename in export.output_file_info.keys():
            assert "//" not in export_filename
        return export

    return _pulp_export_factory


@pytest.fixture
def three_synced_repositories(
    file_bindings,
    file_repository_factory,
    file_remote_factory,
    write_3_iso_file_fixture_data_factory,
    monitor_task,
):
    remotes = [
        file_remote_factory(
            manifest_path=write_3_iso_file_fixture_data_factory(f"pie_{i}"), policy="immediate"
        )
        for i in range(3)
    ]
    repositories = [file_repository_factory(remote=remote.pulp_href) for remote in remotes]
    sync_tasks = [
        file_bindings.RepositoriesFileApi.sync(repository.pulp_href, {}).task
        for repository in repositories
    ]
    [monitor_task(task) for task in sync_tasks]
    repositories = [
        file_bindings.RepositoriesFileApi.read(repository.pulp_href) for repository in repositories
    ]
    return repositories


@pytest.fixture
def repository_with_four_versions(
    file_repository_factory,
    file_bindings,
    random_artifact,
    monitor_task,
):
    repository = file_repository_factory()
    for i in range(3):
        monitor_task(
            file_bindings.ContentFilesApi.create(
                artifact=random_artifact.pulp_href,
                relative_path=f"{i}.dat",
                repository=repository.pulp_href,
            ).task
        )
    return repository


@pytest.fixture
def shallow_pulp_exporter(pulp_exporter_factory):
    return pulp_exporter_factory()


@pytest.fixture
def full_pulp_exporter(
    pulp_exporter_factory,
    three_synced_repositories,
):
    repositories = three_synced_repositories
    return pulp_exporter_factory(repositories=repositories)


@pytest.mark.parallel
def test_crud_exporter(pulpcore_bindings, shallow_pulp_exporter, monitor_task):
    # READ
    exporter = shallow_pulp_exporter
    exporter_read = pulpcore_bindings.ExportersPulpApi.read(exporter.pulp_href)
    assert exporter_read.name == exporter.name
    assert exporter_read.path == exporter.path
    assert len(exporter_read.repositories) == 0

    # UPDATE
    body = {"path": "/tmp/{}".format(str(uuid.uuid4()))}
    result = pulpcore_bindings.ExportersPulpApi.partial_update(exporter.pulp_href, body)
    monitor_task(result.task)
    exporter_read = pulpcore_bindings.ExportersPulpApi.read(exporter.pulp_href)
    assert exporter_read.path != exporter.path
    assert exporter_read.path == body["path"]

    # LIST
    exporters = pulpcore_bindings.ExportersPulpApi.list(name=exporter.name).results
    assert exporter.name in [e.name for e in exporters]

    # DELETE
    result = pulpcore_bindings.ExportersPulpApi.delete(exporter.pulp_href)
    monitor_task(result.task)
    with pytest.raises(ApiException):
        pulpcore_bindings.ExportersPulpApi.read(exporter.pulp_href)


@pytest.mark.parallel
def test_export(pulpcore_bindings, pulp_export_factory, full_pulp_exporter, monitor_task):
    exporter = full_pulp_exporter
    assert len(exporter.repositories) == 3

    # Test export
    export = pulp_export_factory(exporter)

    # Test list and delete
    # export 2 more to test on
    export_href2, export_href3 = (
        monitor_task(
            pulpcore_bindings.ExportersPulpExportsApi.create(exporter.pulp_href, {}).task
        ).created_resources[0]
        for _ in range(2)
    )
    exports = pulpcore_bindings.ExportersPulpExportsApi.list(exporter.pulp_href).results
    assert len(exports) == 3
    pulpcore_bindings.ExportersPulpExportsApi.delete(export.pulp_href)
    pulpcore_bindings.ExportersPulpExportsApi.delete(export_href2)
    exports = pulpcore_bindings.ExportersPulpExportsApi.list(exporter.pulp_href).results
    assert len(exports) == 1
    pulpcore_bindings.ExportersPulpExportsApi.delete(export_href3)
    exports = pulpcore_bindings.ExportersPulpExportsApi.list(exporter.pulp_href).results
    assert len(exports) == 0


@pytest.mark.parallel
def test_export_by_version_and_chunked(
    pulp_exporter_factory,
    pulp_export_factory,
    three_synced_repositories,
):
    repositories = three_synced_repositories
    latest_versions = [r.latest_version_href for r in repositories]
    zeroth_versions = [v_href.replace("/1/", "/0/") for v_href in latest_versions]

    # exporter for one repo. specify one version
    exporter = pulp_exporter_factory(repositories=[repositories[0]])
    body = {"versions": [latest_versions[0]]}
    export = pulp_export_factory(exporter, body)
    assert export.exported_resources[0].endswith("/1/")
    body = {"versions": [zeroth_versions[0]]}
    export = pulp_export_factory(exporter, body)
    assert export.exported_resources[0].endswith("/0/")

    # exporter for one repo. specify one *wrong* version
    with pytest.raises(ApiException, match="must belong to"):
        body = {"versions": [latest_versions[1]]}
        pulp_export_factory(exporter, body)

    # test chunked export
    body = {"chunk_size": "250B"}
    export = pulp_export_factory(exporter, body)
    assert export.output_file_info is not None
    assert len(export.output_file_info) > 1

    # Create a new exporter with two repos
    exporter = pulp_exporter_factory(repositories=[repositories[0], repositories[1]])
    # exporter for two repos, specify one version
    with pytest.raises(ApiException, match="does not match the number"):
        body = {"versions": [latest_versions[0]]}
        pulp_export_factory(exporter, body)

    # exporter for two repos, specify one correct and one *wrong* version
    with pytest.raises(ApiException, match="must belong to"):
        body = {"versions": [latest_versions[0], latest_versions[2]]}
        pulp_export_factory(exporter, body)


@pytest.mark.parallel
def test_export_incremental(
    file_bindings,
    pulp_exporter_factory,
    pulp_export_factory,
    file_repo,
    repository_with_four_versions,
):
    repository = repository_with_four_versions
    versions = file_bindings.RepositoriesFileVersionsApi.list(repository.pulp_href).results

    # create exporter for that repository
    exporter = pulp_exporter_factory(repositories=[repository])

    # negative - ask for an incremental without having a last_export
    body = {"full": False}
    with pytest.raises(ApiException):
        pulp_export_factory(exporter, body)

    # export repo-version[1]-full
    body = {"versions": [versions[1].pulp_href]}
    pulp_export_factory(exporter, body)

    # export repo-version[2]
    body = {"versions": [versions[2].pulp_href], "full": False}
    pulp_export_factory(exporter, body)

    # export repo-latest
    body = {"full": False}
    pulp_export_factory(exporter, body)

    # create a new exporter for that repository
    exporter = pulp_exporter_factory(repositories=[repository])

    # export from version-1 to latest last=v3
    body = {"start_versions": [versions[1].pulp_href], "full": False}
    pulp_export_factory(exporter, body)

    # export from version-1 to version-2, last=v2
    body = {
        "start_versions": [versions[1].pulp_href],
        "versions": [versions[2].pulp_href],
        "full": False,
    }
    pulp_export_factory(exporter, body)

    # negative attempt, start_versions= is not a version
    with pytest.raises(ApiException):
        body = {"start_versions": [repository.pulp_href], "full": False}
        pulp_export_factory(exporter, body)

    # negative attempt, start_versions= and Full=True
    with pytest.raises(ApiException):
        body = {"start_versions": [versions[2].pulp_href], "full": True}
        pulp_export_factory(exporter, body)

    # negative attempt, start_versions= is a version from Some Other Repo
    with pytest.raises(ApiException):
        body = {"start_versions": [file_repo.latest_version_href], "full": False}
        pulp_export_factory(exporter, body)


# Test that cross-domain attempts fail
# Exporter: repository, last-export : create, update
# Export: versions, start_versions
@pytest.mark.skipif(not settings.DOMAIN_ENABLED, reason="Domains not enabled.")
@pytest.mark.parallel
def test_cross_domain_exporter(
    basic_manifest_path,
    file_bindings,
    file_remote_factory,
    gen_object_with_cleanup,
    pulpcore_bindings,
    pulp_export_factory,
    pulp_exporter_factory,
    monitor_task,
):
    # Create two domains
    #   In each, create and sync a repository, create and export an exporter
    # Attempt to create an exporter using the *other domain's* repo
    # Attempt to update the exporter using the *other domain's* repo and last_export
    # Use the exporter and attempt to export the *other domain's* repo-versions

    entities = [{}, {}]
    for e in entities:
        body = {
            "name": str(uuid.uuid4()),
            "storage_class": "pulpcore.app.models.storage.FileSystem",
            "storage_settings": {"MEDIA_ROOT": "/var/lib/pulp/media/"},
        }
        e["domain"] = gen_object_with_cleanup(pulpcore_bindings.DomainsApi, body)
        remote = file_remote_factory(
            manifest_path=basic_manifest_path, policy="immediate", pulp_domain=e["domain"].name
        )

        repo_body = {"name": str(uuid.uuid4()), "remote": remote.pulp_href}
        e["repository"] = gen_object_with_cleanup(
            file_bindings.RepositoriesFileApi, repo_body, pulp_domain=e["domain"].name
        )
        task = file_bindings.RepositoriesFileApi.sync(e["repository"].pulp_href, {}).task
        monitor_task(task)
        e["repository"] = file_bindings.RepositoriesFileApi.read(e["repository"].pulp_href)
        e["exporter"] = pulp_exporter_factory(
            repositories=[e["repository"]], pulp_domain=e["domain"]
        )
        e["export"] = pulp_export_factory(e["exporter"])

    target_domain = entities[1]["domain"]
    # cross-create
    with pytest.raises(BadRequestException) as e:
        pulp_exporter_factory(repositories=[entities[0]["repository"]], pulp_domain=target_domain)
    assert e.value.status == 400
    assert json.loads(e.value.body) == {
        "non_field_errors": [f"Objects must all be a part of the {target_domain.name} domain."]
    }
    # cross-update
    body = {"repositories": [entities[0]["repository"].pulp_href]}
    with pytest.raises(BadRequestException) as e:
        pulpcore_bindings.ExportersPulpApi.partial_update(entities[1]["exporter"].pulp_href, body)
    assert e.value.status == 400
    assert json.loads(e.value.body) == {
        "non_field_errors": [f"Objects must all be a part of the {target_domain.name} domain."]
    }

    body = {"last_export": entities[0]["export"].pulp_href}
    with pytest.raises(BadRequestException) as e:
        pulpcore_bindings.ExportersPulpApi.partial_update(entities[1]["exporter"].pulp_href, body)
    assert e.value.status == 400
    assert json.loads(e.value.body) == {
        "non_field_errors": [f"Objects must all be a part of the {target_domain.name} domain."]
    }

    # cross-export
    with pytest.raises(BadRequestException) as e:
        latest_v = entities[0]["repository"].latest_version_href
        zero_v = latest_v.replace("/1/", "/0/")
        body = {
            "start_versions": [latest_v],
            "versions": [zero_v],
            "full": False,
        }
        pulp_export_factory(entities[1]["exporter"], body)
    assert e.value.status == 400
    msgs = json.loads(e.value.body)
    assert "versions" in msgs
    assert "start_versions" in msgs
    assert msgs["versions"] == [
        "Requested RepositoryVersions must belong to the Repositories named by the Exporter!"
    ]
    assert msgs["start_versions"] == [
        "Requested RepositoryVersions must belong to the Repositories named by the Exporter!"
    ]

@pytest.mark.parallel
def test_export_with_meta(pulpcore_bindings, pulp_export_factory, full_pulp_exporter):
    exporter = full_pulp_exporter
    user_meta = {
        "initiator": "ci",
        "purpose": "export",
        "checksum_type": "md5",  # pulp should override only in TOC JSON
    }

    export = pulp_export_factory(exporter, {"meta": user_meta})

    # toc_info contains exactly user meta (unmodified)
    meta_info = export.toc_info.get("meta", {})
    assert meta_info == user_meta

    # Validate TOC JSON file content
    toc_file_path = export.toc_info.get("file")
    assert toc_file_path and isinstance(toc_file_path, str)

    with open(toc_file_path, "r") as f:
        toc_data = json.load(f)

    meta_json = toc_data.get("meta", {})
    assert meta_json.get("initiator") == "ci"
    assert meta_json.get("purpose") == "export"
    # overridden field check
    assert meta_json.get("checksum_type") == "crc32"
