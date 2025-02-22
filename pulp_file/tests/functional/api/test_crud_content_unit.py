"""Tests that perform actions over content unit."""

import hashlib
import os
import pytest
import uuid

from pulpcore.tests.functional.utils import generate_iso, PulpTaskError


@pytest.mark.parallel
def test_crud_content_unit(file_bindings, random_artifact, gen_object_with_cleanup):
    artifact_attrs = {"artifact": random_artifact.pulp_href, "relative_path": str(uuid.uuid4())}
    content_unit = gen_object_with_cleanup(file_bindings.ContentFilesApi, **artifact_attrs)
    assert content_unit.artifact == random_artifact.pulp_href
    assert content_unit.relative_path == artifact_attrs["relative_path"]

    response = file_bindings.ContentFilesApi.list(relative_path=content_unit.relative_path)
    assert response.count == 1

    content_unit = file_bindings.ContentFilesApi.read(content_unit.pulp_href)
    assert content_unit.artifact == random_artifact.pulp_href
    assert content_unit.relative_path == artifact_attrs["relative_path"]

    with pytest.raises(AttributeError) as exc:
        file_bindings.ContentFilesApi.partial_update(
            content_unit.pulp_href, relative_path=str(uuid.uuid())
        )
    assert exc.value.args[0] == "'ContentFilesApi' object has no attribute 'partial_update'"

    with pytest.raises(AttributeError) as exc:
        file_bindings.ContentFilesApi.update(content_unit.pulp_href, relative_path=str(uuid.uuid()))
    assert exc.value.args[0] == "'ContentFilesApi' object has no attribute 'update'"


@pytest.mark.parallel
def test_same_sha256_same_relative_path_no_repo(file_bindings, random_artifact, monitor_task):
    artifact_attrs = {"artifact": random_artifact.pulp_href, "relative_path": str(uuid.uuid4())}

    content1 = file_bindings.ContentFilesApi.read(
        monitor_task(file_bindings.ContentFilesApi.create(**artifact_attrs).task).created_resources[
            0
        ]
    )
    content2 = file_bindings.ContentFilesApi.read(
        monitor_task(file_bindings.ContentFilesApi.create(**artifact_attrs).task).created_resources[
            0
        ]
    )
    assert content1.pulp_href == content2.pulp_href
    assert file_bindings.ContentFilesApi.read(content1.pulp_href).pulp_href == content2.pulp_href


@pytest.mark.parallel
def test_same_sha256_same_relative_path_repo_specified(
    file_bindings,
    random_artifact,
    gen_user,
    file_repository_factory,
    monitor_task,
):
    max = gen_user(model_roles=["file.filerepository_creator"])
    john = gen_user(model_roles=["file.filerepository_creator"])

    with max:
        repo1 = file_repository_factory(name=str(uuid.uuid4()))
    with john:
        repo2 = file_repository_factory(name=str(uuid.uuid4()))

    artifact_attrs = {"artifact": random_artifact.pulp_href, "relative_path": str(uuid.uuid4())}

    artifact_attrs["repository"] = repo1.pulp_href
    with max:
        response1 = file_bindings.ContentFilesApi.create(**artifact_attrs)
        response2 = file_bindings.ContentFilesApi.create(**artifact_attrs)

    content1 = file_bindings.ContentFilesApi.read(monitor_task(response1.task).created_resources[1])
    content2 = file_bindings.ContentFilesApi.read(monitor_task(response2.task).created_resources[0])
    assert content1.pulp_href == content2.pulp_href
    repo1 = file_bindings.RepositoriesFileApi.read(repo1.pulp_href)
    assert repo1.latest_version_href.endswith("/versions/1/")

    version = file_bindings.RepositoriesFileVersionsApi.read(repo1.latest_version_href)
    assert version.content_summary.present["file.file"]["count"] == 1
    assert version.content_summary.added["file.file"]["count"] == 1

    artifact_attrs["repository"] = repo2.pulp_href
    with john:
        ctask3 = file_bindings.ContentFilesApi.create(**artifact_attrs).task

    content3 = file_bindings.ContentFilesApi.read(monitor_task(ctask3).created_resources[1])
    assert content3.pulp_href == content1.pulp_href
    repo2 = file_bindings.RepositoriesFileApi.read(repo2.pulp_href)
    assert repo2.latest_version_href.endswith("/versions/1/")

    version = file_bindings.RepositoriesFileVersionsApi.read(repo2.latest_version_href)
    assert version.content_summary.present["file.file"]["count"] == 1
    assert version.content_summary.added["file.file"]["count"] == 1


@pytest.mark.parallel
def test_same_sha256_diff_relative_path(file_bindings, random_artifact, gen_object_with_cleanup):
    artifact_attrs = {"artifact": random_artifact.pulp_href, "relative_path": str(uuid.uuid4())}
    gen_object_with_cleanup(file_bindings.ContentFilesApi, **artifact_attrs)

    artifact_attrs["relative_path"] = str(uuid.uuid4())
    artifact_attrs = {"artifact": random_artifact.pulp_href, "relative_path": str(uuid.uuid4())}
    gen_object_with_cleanup(file_bindings.ContentFilesApi, **artifact_attrs)

    response = file_bindings.ContentFilesApi.list(relative_path=artifact_attrs["relative_path"])
    assert response.count == 1


@pytest.mark.parallel
def test_second_content_unit_with_same_rel_path_replaces_the_first(
    file_bindings,
    file_repo,
    random_artifact_factory,
    gen_object_with_cleanup,
):
    latest_repo_version = file_bindings.RepositoriesFileVersionsApi.read(
        file_repo.latest_version_href
    )
    assert latest_repo_version.number == 0

    artifact_attrs = {
        "artifact": random_artifact_factory().pulp_href,
        "relative_path": str(uuid.uuid4()),
        "repository": file_repo.pulp_href,
    }
    gen_object_with_cleanup(file_bindings.ContentFilesApi, **artifact_attrs)

    file_repo = file_bindings.RepositoriesFileApi.read(file_repo.pulp_href)
    latest_repo_version = file_bindings.RepositoriesFileVersionsApi.read(
        file_repo.latest_version_href
    )
    assert latest_repo_version.content_summary.present["file.file"]["count"] == 1
    assert latest_repo_version.number == 1

    artifact_attrs["artifact"] = random_artifact_factory().pulp_href
    gen_object_with_cleanup(file_bindings.ContentFilesApi, **artifact_attrs)

    file_repo = file_bindings.RepositoriesFileApi.read(file_repo.pulp_href)
    latest_repo_version = file_bindings.RepositoriesFileVersionsApi.read(
        file_repo.latest_version_href
    )
    assert latest_repo_version.content_summary.present["file.file"]["count"] == 1
    assert latest_repo_version.number == 2


@pytest.mark.parallel
def test_cannot_create_repo_version_with_two_relative_paths_the_same(
    file_bindings,
    file_repo,
    random_artifact_factory,
    gen_object_with_cleanup,
    monitor_task,
):
    latest_repo_version = file_bindings.RepositoriesFileVersionsApi.read(
        file_repo.latest_version_href
    )
    assert latest_repo_version.number == 0

    artifact_attrs = {
        "artifact": random_artifact_factory().pulp_href,
        "relative_path": str(uuid.uuid4()),
    }
    first_content_unit = gen_object_with_cleanup(file_bindings.ContentFilesApi, **artifact_attrs)

    artifact_attrs["artifact"] = random_artifact_factory().pulp_href
    second_content_unit = gen_object_with_cleanup(file_bindings.ContentFilesApi, **artifact_attrs)

    response = file_bindings.ContentFilesApi.list(relative_path=first_content_unit.relative_path)
    assert response.count == 2

    data = {"add_content_units": [first_content_unit.pulp_href, second_content_unit.pulp_href]}

    with pytest.raises(PulpTaskError):
        response = file_bindings.RepositoriesFileApi.modify(file_repo.pulp_href, data)
        monitor_task(response.task)


@pytest.mark.parallel
@pytest.mark.parametrize(
    "bad_input",
    [
        pytest.param([()], id="list_with_empty_dict"),
        # Pydantic ignores the superfluous parameters for us.
        pytest.param({"a": "b"}, id="dict", marks=pytest.mark.xfail),
        pytest.param(["/content/"], id="list"),
    ],
)
def test_modify_rejects_bad_input(file_bindings, file_repo, bad_input):
    with pytest.raises((file_bindings.module.ApiException, ValueError)):
        file_bindings.RepositoriesFileApi.modify(file_repo.pulp_href, bad_input)


@pytest.mark.parallel
def test_create_file_content_from_chunked_upload(
    pulpcore_bindings,
    file_bindings,
    tmp_path,
    gen_object_with_cleanup,
    monitor_task,
):
    hasher = hashlib.sha256()
    file_1 = tmp_path / "file.part1"
    file_1.write_bytes(os.urandom(128))
    hasher.update(file_1.read_bytes())
    file_2 = tmp_path / "file.part2"
    file_2.write_bytes(os.urandom(128))
    hasher.update(file_2.read_bytes())
    expected_digest = hasher.hexdigest()

    # Perform the same test twice, because in the second run, the existing artifact should be
    # reused.
    for _ in (0, 1):
        # Upload the file and generate content
        upload = gen_object_with_cleanup(pulpcore_bindings.UploadsApi, {"size": 256})
        pulpcore_bindings.UploadsApi.update(
            upload_href=upload.pulp_href, file=str(file_1), content_range="bytes 0-127/256"
        )
        pulpcore_bindings.UploadsApi.update(
            upload_href=upload.pulp_href, file=str(file_2), content_range="bytes 128-255/256"
        )
        most_recent_path = str(uuid.uuid4())
        response = file_bindings.ContentFilesApi.create(
            upload=upload.pulp_href, relative_path=most_recent_path
        )
        task = monitor_task(response.task)
        content = file_bindings.ContentFilesApi.read(task.created_resources[0])
        assert content.sha256 == expected_digest
        # Upload gets deleted if the content gets created
        with pytest.raises(pulpcore_bindings.module.ApiException):
            pulpcore_bindings.UploadsApi.read(upload.pulp_href)

    # Attempt to create a duplicate content by re-using the most recent relative path
    upload = gen_object_with_cleanup(pulpcore_bindings.UploadsApi, {"size": 256})
    pulpcore_bindings.UploadsApi.update(
        upload_href=upload.pulp_href, file=str(file_1), content_range="bytes 0-127/256"
    )
    pulpcore_bindings.UploadsApi.update(
        upload_href=upload.pulp_href, file=str(file_2), content_range="bytes 128-255/256"
    )
    response = file_bindings.ContentFilesApi.create(
        upload=upload.pulp_href, relative_path=most_recent_path
    )
    task = monitor_task(response.task)
    content = file_bindings.ContentFilesApi.read(task.created_resources[0])
    assert content.sha256 == expected_digest
    # Upload gets deleted even though no new content got created
    with pytest.raises(pulpcore_bindings.module.ApiException):
        pulpcore_bindings.UploadsApi.read(upload.pulp_href)


@pytest.mark.parallel
def test_create_file_from_url(
    file_bindings,
    file_repository_factory,
    file_remote_factory,
    distribution_base_url,
    file_distribution_factory,
    basic_manifest_path,
    monitor_task,
):
    # Test create w/ url
    remote = file_remote_factory(manifest_path=basic_manifest_path)
    body = {"file_url": remote.url, "relative_path": "PULP_MANIFEST"}
    response = file_bindings.ContentFilesApi.create(**body)
    task = monitor_task(response.task)
    assert len(task.created_resources) == 1
    assert "api/v3/content/file/files/" in task.created_resources[0]
    # Set up
    repo1 = file_repository_factory(autopublish=True)
    body = {"remote": remote.pulp_href}
    monitor_task(file_bindings.RepositoriesFileApi.sync(repo1.pulp_href, body).task)
    distro = file_distribution_factory(repository=repo1.pulp_href)
    content = file_bindings.ContentFilesApi.list(
        repository_version=f"{repo1.versions_href}1/", relative_path="1.iso"
    ).results[0]

    # Test create w/ url for already existing content
    response = file_bindings.ContentFilesApi.create(
        file_url=f"{distribution_base_url(distro.base_url)}1.iso",
        relative_path="1.iso",
    )
    task = monitor_task(response.task)
    assert len(task.created_resources) == 1
    assert task.created_resources[0] == content.pulp_href


def _remove_artifact(file_path):
    assert os.path.exists(file_path)
    os.remove(file_path)
    assert not os.path.exists(file_path)


def _prep_iso(path, root):
    file_path = path / str(uuid.uuid4())
    iso_attrs = generate_iso(file_path)
    iso_path = os.path.join(root, "artifact", iso_attrs["digest"][0:2], iso_attrs["digest"][2:])
    return file_path, iso_attrs, iso_path


@pytest.mark.parallel
def test_reupload_damaged_artifact_atomic(
    file_bindings,
    file_repository_factory,
    monitor_task,
    pulp_settings,
    tmp_path,
):
    if pulp_settings.STORAGES["default"]["BACKEND"] != "pulpcore.app.models.storage.FileSystem":
        pytest.skip("this test only works for filesystem storage")
    file_path, iso_attrs, iso_path = _prep_iso(tmp_path, pulp_settings.MEDIA_ROOT)

    # Create a repo and add a file to it
    repo = file_repository_factory(name=str(uuid.uuid4()))
    create_attrs = {"file": str(file_path), "relative_path": "1.iso", "repository": repo.prn}
    monitor_task(file_bindings.ContentFilesApi.create(**create_attrs).task)

    # Delete the artifact-storage for that artifact
    _remove_artifact(iso_path)

    # Attempt atomic re-upload - expect success
    monitor_task(file_bindings.ContentFilesApi.create(**create_attrs).task)
    # Check presence of artifact
    assert os.path.exists(iso_path)


@pytest.mark.parallel
def test_reupload_damaged_artifact_chunked(
    file_bindings,
    gen_object_with_cleanup,
    monitor_task,
    pulpcore_bindings,
    pulp_settings,
    tmp_path,
):
    if pulp_settings.STORAGES["default"]["BACKEND"] != "pulpcore.app.models.storage.FileSystem":
        pytest.skip("this test only works for filesystem storage")
    file_path, iso_attrs, iso_path = _prep_iso(tmp_path, pulp_settings.MEDIA_ROOT)

    # Attempt chunked-upload - expect success
    upload = gen_object_with_cleanup(pulpcore_bindings.UploadsApi, {"size": iso_attrs["size"]})

    pulpcore_bindings.UploadsApi.update(
        upload_href=upload.pulp_href,
        file=str(file_path),
        content_range=f"bytes 0-{iso_attrs['size']-1}/{iso_attrs['size']}",
    )
    response = file_bindings.ContentFilesApi.create(upload=upload.pulp_href, relative_path="1.iso")
    monitor_task(response.task)
    # Check presence of artifact
    assert os.path.exists(iso_path)
    # Delete the artifact-storage for that artifact
    _remove_artifact(iso_path)

    # Attempt a second timed - expect success
    upload = gen_object_with_cleanup(pulpcore_bindings.UploadsApi, {"size": iso_attrs["size"]})
    pulpcore_bindings.UploadsApi.update(
        upload_href=upload.pulp_href,
        file=str(file_path),
        content_range=f"bytes 0-{iso_attrs['size']-1}/{iso_attrs['size']}",
    )
    response = file_bindings.ContentFilesApi.create(upload=upload.pulp_href, relative_path="1.iso")
    monitor_task(response.task)
    # Check presence of artifact
    assert os.path.exists(iso_path)
