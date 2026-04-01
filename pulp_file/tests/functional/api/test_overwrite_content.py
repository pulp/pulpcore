"""Tests for the repository content overwrite protection feature."""

import uuid

import pytest

from pulpcore.client.pulp_file.exceptions import ApiException
from pulpcore.tests.functional.utils import PulpTaskError


@pytest.mark.parallel
def test_modify_overwrite_false_rejects_overwrite(
    file_bindings,
    file_repo,
    file_content_unit_with_name_factory,
    monitor_task,
):
    """Adding content with a conflicting relative_path and overwrite=False returns a 409."""
    shared_path = str(uuid.uuid4())

    # Create two content units that share the same relative_path but have different artifacts
    content_a = file_content_unit_with_name_factory(shared_path)
    content_b = file_content_unit_with_name_factory(shared_path)
    assert content_a.pulp_href != content_b.pulp_href

    # Add the first content unit (overwrite is irrelevant for an empty repo)
    monitor_task(
        file_bindings.RepositoriesFileApi.modify(
            file_repo.pulp_href,
            {"add_content_units": [content_a.pulp_href]},
        ).task
    )
    repo = file_bindings.RepositoriesFileApi.read(file_repo.pulp_href)
    assert repo.latest_version_href.endswith("/versions/1/")

    # Attempt to add the second content unit with overwrite=False — expect HTTP 409
    with pytest.raises(ApiException) as exc_info:
        file_bindings.RepositoriesFileApi.modify(
            file_repo.pulp_href,
            {"add_content_units": [content_b.pulp_href], "overwrite": False},
        )
    assert exc_info.value.status == 409
    assert "PLP0023" in exc_info.value.body

    # Repo version should not have advanced
    repo = file_bindings.RepositoriesFileApi.read(file_repo.pulp_href)
    assert repo.latest_version_href.endswith("/versions/1/")


@pytest.mark.parallel
def test_modify_overwrite_false_allows_non_conflicting(
    file_bindings,
    file_repo,
    file_content_unit_with_name_factory,
    monitor_task,
):
    """Adding content without a conflicting relative_path and overwrite=False succeeds."""
    content_a = file_content_unit_with_name_factory(str(uuid.uuid4()))
    content_b = file_content_unit_with_name_factory(str(uuid.uuid4()))

    # Add the first content unit
    monitor_task(
        file_bindings.RepositoriesFileApi.modify(
            file_repo.pulp_href,
            {"add_content_units": [content_a.pulp_href], "overwrite": False},
        ).task
    )
    repo = file_bindings.RepositoriesFileApi.read(file_repo.pulp_href)
    assert repo.latest_version_href.endswith("/versions/1/")

    # Add non-conflicting content with overwrite=False — should succeed
    monitor_task(
        file_bindings.RepositoriesFileApi.modify(
            file_repo.pulp_href,
            {"add_content_units": [content_b.pulp_href], "overwrite": False},
        ).task
    )
    repo = file_bindings.RepositoriesFileApi.read(file_repo.pulp_href)
    assert repo.latest_version_href.endswith("/versions/2/")


@pytest.mark.parallel
def test_modify_default_allows_overwrite(
    file_bindings,
    file_repo,
    file_content_unit_with_name_factory,
    monitor_task,
):
    """Default modify (overwrite=True) still allows overwriting content."""
    shared_path = str(uuid.uuid4())
    content_a = file_content_unit_with_name_factory(shared_path)
    content_b = file_content_unit_with_name_factory(shared_path)

    monitor_task(
        file_bindings.RepositoriesFileApi.modify(
            file_repo.pulp_href,
            {"add_content_units": [content_a.pulp_href]},
        ).task
    )
    repo = file_bindings.RepositoriesFileApi.read(file_repo.pulp_href)
    assert repo.latest_version_href.endswith("/versions/1/")

    # With default overwrite=True, adding conflicting content succeeds
    monitor_task(
        file_bindings.RepositoriesFileApi.modify(
            file_repo.pulp_href,
            {"add_content_units": [content_b.pulp_href]},
        ).task
    )
    repo = file_bindings.RepositoriesFileApi.read(file_repo.pulp_href)
    assert repo.latest_version_href.endswith("/versions/2/")


@pytest.mark.parallel
def test_modify_overwrite_false_allows_replace_when_removing_conflict(
    file_bindings,
    file_repo,
    file_content_unit_with_name_factory,
    monitor_task,
):
    """Replacing content with overwrite=False succeeds when the conflicting unit is removed."""
    shared_path = str(uuid.uuid4())
    content_a = file_content_unit_with_name_factory(shared_path)
    content_b = file_content_unit_with_name_factory(shared_path)

    # Seed the repo with content_a
    monitor_task(
        file_bindings.RepositoriesFileApi.modify(
            file_repo.pulp_href,
            {"add_content_units": [content_a.pulp_href]},
        ).task
    )
    repo = file_bindings.RepositoriesFileApi.read(file_repo.pulp_href)
    assert repo.latest_version_href.endswith("/versions/1/")

    # Remove content_a and add content_b in the same call with overwrite=False — should succeed
    monitor_task(
        file_bindings.RepositoriesFileApi.modify(
            file_repo.pulp_href,
            {
                "remove_content_units": [content_a.pulp_href],
                "add_content_units": [content_b.pulp_href],
                "overwrite": False,
            },
        ).task
    )
    repo = file_bindings.RepositoriesFileApi.read(file_repo.pulp_href)
    assert repo.latest_version_href.endswith("/versions/2/")


@pytest.mark.parallel
def test_content_upload_overwrite_false_rejects_overwrite(
    file_bindings,
    file_repo,
    random_artifact_factory,
    monitor_task,
):
    """Uploading content with overwrite=False and a conflicting relative_path is rejected."""
    shared_path = str(uuid.uuid4())

    # Upload first content unit into the repo
    artifact_a = random_artifact_factory()
    monitor_task(
        file_bindings.ContentFilesApi.create(
            relative_path=shared_path,
            artifact=artifact_a.pulp_href,
            repository=file_repo.pulp_href,
        ).task
    )
    repo = file_bindings.RepositoriesFileApi.read(file_repo.pulp_href)
    assert repo.latest_version_href.endswith("/versions/1/")

    # Attempt to upload a second content unit with the same relative_path and overwrite=False
    artifact_b = random_artifact_factory()
    with pytest.raises(PulpTaskError) as exc_info:
        monitor_task(
            file_bindings.ContentFilesApi.create(
                relative_path=shared_path,
                artifact=artifact_b.pulp_href,
                repository=file_repo.pulp_href,
                overwrite=False,
            ).task
        )
    assert exc_info.value.task.error["description"]
    assert "PLP0023" in exc_info.value.task.error["description"]

    # Repo version should not have advanced
    repo = file_bindings.RepositoriesFileApi.read(file_repo.pulp_href)
    assert repo.latest_version_href.endswith("/versions/1/")


@pytest.mark.parallel
def test_content_upload_overwrite_false_allows_non_conflicting(
    file_bindings,
    file_repo,
    random_artifact_factory,
    monitor_task,
):
    """Uploading content with overwrite=False and no conflict succeeds."""
    # Upload first content unit into the repo with overwrite=False
    artifact_a = random_artifact_factory()
    monitor_task(
        file_bindings.ContentFilesApi.create(
            relative_path=str(uuid.uuid4()),
            artifact=artifact_a.pulp_href,
            repository=file_repo.pulp_href,
            overwrite=False,
        ).task
    )
    repo = file_bindings.RepositoriesFileApi.read(file_repo.pulp_href)
    assert repo.latest_version_href.endswith("/versions/1/")

    # Upload a second content unit with a different relative_path
    artifact_b = random_artifact_factory()
    monitor_task(
        file_bindings.ContentFilesApi.create(
            relative_path=str(uuid.uuid4()),
            artifact=artifact_b.pulp_href,
            repository=file_repo.pulp_href,
            overwrite=False,
        ).task
    )
    repo = file_bindings.RepositoriesFileApi.read(file_repo.pulp_href)
    assert repo.latest_version_href.endswith("/versions/2/")
