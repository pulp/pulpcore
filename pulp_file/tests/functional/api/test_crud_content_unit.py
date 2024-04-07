"""Tests that perform actions over content unit."""

import hashlib
import os
import pytest
import uuid

from pulpcore.tests.functional.utils import PulpTaskError

from pulpcore.client.pulpcore.exceptions import ApiException as coreApiException
from pulpcore.client.pulp_file.exceptions import ApiException


@pytest.mark.parallel
def test_crud_content_unit(random_artifact, file_content_api_client, gen_object_with_cleanup):
    artifact_attrs = {"artifact": random_artifact.pulp_href, "relative_path": str(uuid.uuid4())}
    content_unit = gen_object_with_cleanup(file_content_api_client, **artifact_attrs)
    assert content_unit.artifact == random_artifact.pulp_href
    assert content_unit.relative_path == artifact_attrs["relative_path"]

    response = file_content_api_client.list(relative_path=content_unit.relative_path)
    assert response.count == 1

    content_unit = file_content_api_client.read(content_unit.pulp_href)
    assert content_unit.artifact == random_artifact.pulp_href
    assert content_unit.relative_path == artifact_attrs["relative_path"]

    with pytest.raises(AttributeError) as exc:
        file_content_api_client.partial_update(
            content_unit.pulp_href, relative_path=str(uuid.uuid())
        )
    assert exc.value.args[0] == "'ContentFilesApi' object has no attribute 'partial_update'"

    with pytest.raises(AttributeError) as exc:
        file_content_api_client.update(content_unit.pulp_href, relative_path=str(uuid.uuid()))
    assert exc.value.args[0] == "'ContentFilesApi' object has no attribute 'update'"


@pytest.mark.parallel
def test_same_sha256_same_relative_path_no_repo(
    random_artifact,
    file_content_api_client,
    monitor_task,
):
    artifact_attrs = {"artifact": random_artifact.pulp_href, "relative_path": str(uuid.uuid4())}

    content1 = file_content_api_client.read(
        monitor_task(file_content_api_client.create(**artifact_attrs).task).created_resources[0]
    )
    content2 = file_content_api_client.read(
        monitor_task(file_content_api_client.create(**artifact_attrs).task).created_resources[0]
    )
    assert content1.pulp_href == content2.pulp_href
    assert file_content_api_client.read(content1.pulp_href).pulp_href == content2.pulp_href


@pytest.mark.parallel
def test_same_sha256_same_relative_path_repo_specified(
    random_artifact,
    file_content_api_client,
    file_bindings,
    file_repository_version_api_client,
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
        response1 = file_content_api_client.create(**artifact_attrs)
        response2 = file_content_api_client.create(**artifact_attrs)

    content1 = file_content_api_client.read(monitor_task(response1.task).created_resources[1])
    content2 = file_content_api_client.read(monitor_task(response2.task).created_resources[0])
    assert content1.pulp_href == content2.pulp_href
    repo1 = file_bindings.RepositoriesFileApi.read(repo1.pulp_href)
    assert repo1.latest_version_href.endswith("/versions/1/")

    version = file_repository_version_api_client.read(repo1.latest_version_href)
    assert version.content_summary.present["file.file"]["count"] == 1
    assert version.content_summary.added["file.file"]["count"] == 1

    artifact_attrs["repository"] = repo2.pulp_href
    with john:
        ctask3 = file_content_api_client.create(**artifact_attrs).task

    content3 = file_content_api_client.read(monitor_task(ctask3).created_resources[1])
    assert content3.pulp_href == content1.pulp_href
    repo2 = file_bindings.RepositoriesFileApi.read(repo2.pulp_href)
    assert repo2.latest_version_href.endswith("/versions/1/")

    version = file_repository_version_api_client.read(repo2.latest_version_href)
    assert version.content_summary.present["file.file"]["count"] == 1
    assert version.content_summary.added["file.file"]["count"] == 1


@pytest.mark.parallel
def test_same_sha256_diff_relative_path(
    random_artifact, file_content_api_client, gen_object_with_cleanup
):
    artifact_attrs = {"artifact": random_artifact.pulp_href, "relative_path": str(uuid.uuid4())}
    gen_object_with_cleanup(file_content_api_client, **artifact_attrs)

    artifact_attrs["relative_path"] = str(uuid.uuid4())
    artifact_attrs = {"artifact": random_artifact.pulp_href, "relative_path": str(uuid.uuid4())}
    gen_object_with_cleanup(file_content_api_client, **artifact_attrs)

    response = file_content_api_client.list(relative_path=artifact_attrs["relative_path"])
    assert response.count == 1


@pytest.mark.parallel
def test_second_content_unit_with_same_rel_path_replaces_the_first(
    file_repo,
    random_artifact_factory,
    file_content_api_client,
    gen_object_with_cleanup,
    file_repository_version_api_client,
    file_bindings,
):
    latest_repo_version = file_repository_version_api_client.read(file_repo.latest_version_href)
    assert latest_repo_version.number == 0

    artifact_attrs = {
        "artifact": random_artifact_factory().pulp_href,
        "relative_path": str(uuid.uuid4()),
        "repository": file_repo.pulp_href,
    }
    gen_object_with_cleanup(file_content_api_client, **artifact_attrs)

    file_repo = file_bindings.RepositoriesFileApi.read(file_repo.pulp_href)
    latest_repo_version = file_repository_version_api_client.read(file_repo.latest_version_href)
    assert latest_repo_version.content_summary.present["file.file"]["count"] == 1
    assert latest_repo_version.number == 1

    artifact_attrs["artifact"] = random_artifact_factory().pulp_href
    gen_object_with_cleanup(file_content_api_client, **artifact_attrs)

    file_repo = file_bindings.RepositoriesFileApi.read(file_repo.pulp_href)
    latest_repo_version = file_repository_version_api_client.read(file_repo.latest_version_href)
    assert latest_repo_version.content_summary.present["file.file"]["count"] == 1
    assert latest_repo_version.number == 2


@pytest.mark.parallel
def test_cannot_create_repo_version_with_two_relative_paths_the_same(
    file_repo,
    random_artifact_factory,
    file_content_api_client,
    gen_object_with_cleanup,
    file_repository_version_api_client,
    file_bindings,
    monitor_task,
):
    latest_repo_version = file_repository_version_api_client.read(file_repo.latest_version_href)
    assert latest_repo_version.number == 0

    artifact_attrs = {
        "artifact": random_artifact_factory().pulp_href,
        "relative_path": str(uuid.uuid4()),
    }
    first_content_unit = gen_object_with_cleanup(file_content_api_client, **artifact_attrs)

    artifact_attrs["artifact"] = random_artifact_factory().pulp_href
    second_content_unit = gen_object_with_cleanup(file_content_api_client, **artifact_attrs)

    response = file_content_api_client.list(relative_path=first_content_unit.relative_path)
    assert response.count == 2

    data = {"add_content_units": [first_content_unit.pulp_href, second_content_unit.pulp_href]}

    with pytest.raises(PulpTaskError):
        response = file_bindings.RepositoriesFileApi.modify(file_repo.pulp_href, data)
        monitor_task(response.task)


@pytest.mark.parallel
def test_bad_inputs_to_modify_endpoint(file_repo, file_bindings, needs_pulp_plugin):
    needs_pulp_plugin("core", min="3.23.0.dev")

    with pytest.raises(ApiException):
        file_bindings.RepositoriesFileApi.modify(file_repo.pulp_href, [{}])

    with pytest.raises(ApiException):
        file_bindings.RepositoriesFileApi.modify(file_repo.pulp_href, {"a": "b"})

    with pytest.raises(ApiException):
        file_bindings.RepositoriesFileApi.modify(file_repo.pulp_href, ["/content/"])


@pytest.mark.parallel
def test_create_file_content_from_chunked_upload(
    tmp_path,
    gen_object_with_cleanup,
    uploads_api_client,
    file_content_api_client,
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
        upload = gen_object_with_cleanup(uploads_api_client, {"size": 256})
        uploads_api_client.update(
            upload_href=upload.pulp_href, file=file_1, content_range="bytes 0-127/256"
        )
        uploads_api_client.update(
            upload_href=upload.pulp_href, file=file_2, content_range="bytes 128-255/256"
        )
        most_recent_path = str(uuid.uuid4())
        response = file_content_api_client.create(
            upload=upload.pulp_href, relative_path=most_recent_path
        )
        task = monitor_task(response.task)
        content = file_content_api_client.read(task.created_resources[0])
        assert content.sha256 == expected_digest
        # Upload gets deleted if the content gets created
        with pytest.raises(coreApiException):
            uploads_api_client.read(upload.pulp_href)

    # Attempt to create a duplicate content by re-using the most recent relative path
    upload = gen_object_with_cleanup(uploads_api_client, {"size": 256})
    uploads_api_client.update(
        upload_href=upload.pulp_href, file=file_1, content_range="bytes 0-127/256"
    )
    uploads_api_client.update(
        upload_href=upload.pulp_href, file=file_2, content_range="bytes 128-255/256"
    )
    response = file_content_api_client.create(
        upload=upload.pulp_href, relative_path=most_recent_path
    )
    task = monitor_task(response.task)
    content = file_content_api_client.read(task.created_resources[0])
    assert content.sha256 == expected_digest
    # Upload gets deleted even though no new content got created
    with pytest.raises(coreApiException):
        uploads_api_client.read(upload.pulp_href)
