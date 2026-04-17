"""Tests that sync file plugin repositories."""

import pytest

from pulpcore.client.pulp_file import (
    RepositorySyncURL,
)
from pulpcore.tests.functional.utils import get_files_in_manifest


@pytest.fixture
def file_repo_with_auto_publish(file_repository_factory):
    return file_repository_factory(autopublish=True, manifest="TEST_MANIFEST")


@pytest.mark.parallel
def test_auto_publish_and_distribution(
    file_bindings,
    distribution_base_url,
    file_repo_with_auto_publish,
    file_remote_ssl_factory,
    basic_manifest_path,
    gen_object_with_cleanup,
    file_random_content_unit,
    monitor_task,
    has_pulp_plugin,
):
    """Tests auto-publish and auto-distribution"""
    remote = file_remote_ssl_factory(manifest_path=basic_manifest_path, policy="on_demand")
    repo = file_bindings.RepositoriesFileApi.read(file_repo_with_auto_publish.pulp_href)
    distribution = gen_object_with_cleanup(
        file_bindings.DistributionsFileApi,
        {"name": "foo", "base_path": "bar/foo", "repository": repo.pulp_href},
    )
    distribution_base_url = distribution_base_url(distribution.base_url)

    # Assert that the repository is at version 0 and that there are no publications associated with
    # this Repository and that the distribution doesn't have a publication associated with it.
    assert repo.latest_version_href.endswith("/versions/0/")
    assert file_bindings.PublicationsFileApi.list(repository=repo.pulp_href).count == 0
    assert (
        file_bindings.PublicationsFileApi.list(repository_version=repo.latest_version_href).count
        == 0
    )
    assert distribution.publication is None

    # Check what content and artifacts are in the fixture repository
    expected_files = get_files_in_manifest(remote.url)

    # Sync from the remote
    body = RepositorySyncURL(remote=remote.pulp_href)
    monitor_task(file_bindings.RepositoriesFileApi.sync(repo.pulp_href, body).task)
    repo = file_bindings.RepositoriesFileApi.read(repo.pulp_href)

    # Assert that a new repository version was created and a publication was created
    assert repo.latest_version_href.endswith("/versions/1/")
    assert file_bindings.PublicationsFileApi.list(repository=repo.pulp_href).count == 1
    assert (
        file_bindings.PublicationsFileApi.list(repository_version=repo.latest_version_href).count
        == 1
    )

    # Assert that the publication has a custom manifest
    publication = file_bindings.PublicationsFileApi.list(
        repository_version=repo.latest_version_href
    ).results[0]
    assert publication.manifest == "TEST_MANIFEST"

    # Download the custom manifest
    files_in_first_publication = get_files_in_manifest(
        "{}{}".format(distribution_base_url, publication.manifest)
    )
    assert files_in_first_publication == expected_files

    # Assert that mirror=True is not allowed when autopublish=True
    body = RepositorySyncURL(remote=remote.pulp_href, mirror=True)
    with pytest.raises(file_bindings.ApiException) as exc:
        file_bindings.RepositoriesFileApi.sync(repo.pulp_href, body)
    assert exc.value.status == 400
    assert "Cannot use mirror mode with autopublished repository." in exc.value.body

    # Add a new content unit to the repository and assert that a publication gets created and the
    # new content unit is in it
    monitor_task(
        file_bindings.RepositoriesFileApi.modify(
            repo.pulp_href, {"add_content_units": [file_random_content_unit.pulp_href]}
        ).task
    )
    repo = file_bindings.RepositoriesFileApi.read(repo.pulp_href)
    files_in_second_publication = get_files_in_manifest(
        "{}{}".format(distribution_base_url, publication.manifest)
    )
    files_added = files_in_second_publication - files_in_first_publication
    assert repo.latest_version_href.endswith("/versions/2/")
    assert file_bindings.PublicationsFileApi.list(repository=repo.pulp_href).count == 2
    assert (
        file_bindings.PublicationsFileApi.list(repository_version=repo.latest_version_href).count
        == 1
    )
    assert len(files_added) == 1
    assert list(files_added)[0][1] == file_random_content_unit.sha256

    if has_pulp_plugin("core", min="3.23.0"):
        # Assert that filtering distributions by repository is possible
        distros = file_bindings.DistributionsFileApi.list(repository=repo.pulp_href).results
        assert len(distros) == 1

        distros = file_bindings.DistributionsFileApi.list(repository__in=[repo.pulp_href]).results
        assert len(distros) == 1

        # Assert that no results are returned when filtering by non-existent repository
        nonexistent_repository_href = f"{repo.pulp_href[:-37]}12345678-1234-1234-1234-012345678912/"
        distros = file_bindings.DistributionsFileApi.list(
            repository=nonexistent_repository_href
        ).results


@pytest.mark.parallel
def test_modify_with_publish(
    file_bindings,
    file_repository_factory,
    file_random_content_unit,
    monitor_task,
):
    """Test that passing publish=True to modify creates a publication."""
    repo = file_repository_factory(manifest="TEST_MANIFEST")
    repo = file_bindings.RepositoriesFileApi.read(repo.pulp_href)

    # Verify no publications exist yet
    assert file_bindings.PublicationsFileApi.list(repository=repo.pulp_href).count == 0

    # Modify the repository with publish=True
    monitor_task(
        file_bindings.RepositoriesFileApi.modify(
            repo.pulp_href,
            {
                "add_content_units": [file_random_content_unit.pulp_href],
                "publish": True,
            },
        ).task
    )
    repo = file_bindings.RepositoriesFileApi.read(repo.pulp_href)

    # A new version should have been created and a publication should exist
    assert repo.latest_version_href.endswith("/versions/1/")
    assert file_bindings.PublicationsFileApi.list(repository=repo.pulp_href).count == 1
    assert (
        file_bindings.PublicationsFileApi.list(repository_version=repo.latest_version_href).count
        == 1
    )

    # Verify the publication uses the custom manifest from the repository
    publication = file_bindings.PublicationsFileApi.list(
        repository_version=repo.latest_version_href
    ).results[0]
    assert publication.manifest == "TEST_MANIFEST"

    # Verify the publication's repository version contains the content unit
    content = file_bindings.ContentFilesApi.list(
        repository_version=repo.latest_version_href
    ).results
    content_hrefs = [c.pulp_href for c in content]
    assert file_random_content_unit.pulp_href in content_hrefs


@pytest.mark.parallel
def test_modify_without_publish(
    file_bindings,
    file_repo,
    file_random_content_unit,
    monitor_task,
):
    """Test that modify without publish=True does not create a publication."""
    repo = file_bindings.RepositoriesFileApi.read(file_repo.pulp_href)

    # Modify the repository without publish
    monitor_task(
        file_bindings.RepositoriesFileApi.modify(
            repo.pulp_href,
            {"add_content_units": [file_random_content_unit.pulp_href]},
        ).task
    )
    repo = file_bindings.RepositoriesFileApi.read(repo.pulp_href)

    # A new version should have been created but no publication
    assert repo.latest_version_href.endswith("/versions/1/")
    assert file_bindings.PublicationsFileApi.list(repository=repo.pulp_href).count == 0
