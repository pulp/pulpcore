"""Tests that sync file plugin repositories."""

import pytest

from pulpcore.tests.functional.utils import get_files_in_manifest

from pulpcore.client.pulp_file import (
    RepositorySyncURL,
)


@pytest.fixture
def file_repo_with_auto_publish(file_repository_factory):
    return file_repository_factory(autopublish=True, manifest="TEST_MANIFEST")


@pytest.mark.parallel
def test_auto_publish_and_distribution(
    file_repo_with_auto_publish,
    file_remote_ssl_factory,
    file_bindings,
    file_publication_api_client,
    basic_manifest_path,
    gen_object_with_cleanup,
    file_distribution_api_client,
    file_random_content_unit,
    monitor_task,
    has_pulp_plugin,
):
    """Tests auto-publish and auto-distribution"""
    remote = file_remote_ssl_factory(manifest_path=basic_manifest_path, policy="on_demand")
    repo = file_bindings.RepositoriesFileApi.read(file_repo_with_auto_publish.pulp_href)
    distribution = gen_object_with_cleanup(
        file_distribution_api_client,
        {"name": "foo", "base_path": "bar/foo", "repository": repo.pulp_href},
    )

    # Assert that the repository is at version 0 and that there are no publications associated with
    # this Repository and that the distribution doesn't have a publication associated with it.
    assert repo.latest_version_href.endswith("/versions/0/")
    assert file_publication_api_client.list(repository=repo.pulp_href).count == 0
    assert file_publication_api_client.list(repository_version=repo.latest_version_href).count == 0
    assert distribution.publication is None

    # Check what content and artifacts are in the fixture repository
    expected_files = get_files_in_manifest(remote.url)

    # Sync from the remote
    body = RepositorySyncURL(remote=remote.pulp_href)
    monitor_task(file_bindings.RepositoriesFileApi.sync(repo.pulp_href, body).task)
    repo = file_bindings.RepositoriesFileApi.read(repo.pulp_href)

    # Assert that a new repository version was created and a publication was created
    assert repo.latest_version_href.endswith("/versions/1/")
    assert file_publication_api_client.list(repository=repo.pulp_href).count == 1
    assert file_publication_api_client.list(repository_version=repo.latest_version_href).count == 1

    # Assert that the publication has a custom manifest
    publication = file_publication_api_client.list(
        repository_version=repo.latest_version_href
    ).results[0]
    assert publication.manifest == "TEST_MANIFEST"

    # Download the custom manifest
    files_in_first_publication = get_files_in_manifest(
        "{}{}".format(distribution.base_url, publication.manifest)
    )
    assert files_in_first_publication == expected_files

    # Add a new content unit to the repository and assert that a publication gets created and the
    # new content unit is in it
    monitor_task(
        file_bindings.RepositoriesFileApi.modify(
            repo.pulp_href, {"add_content_units": [file_random_content_unit.pulp_href]}
        ).task
    )
    repo = file_bindings.RepositoriesFileApi.read(repo.pulp_href)
    files_in_second_publication = get_files_in_manifest(
        "{}{}".format(distribution.base_url, publication.manifest)
    )
    files_added = files_in_second_publication - files_in_first_publication
    assert repo.latest_version_href.endswith("/versions/2/")
    assert file_publication_api_client.list(repository=repo.pulp_href).count == 2
    assert file_publication_api_client.list(repository_version=repo.latest_version_href).count == 1
    assert len(files_added) == 1
    assert list(files_added)[0][1] == file_random_content_unit.sha256

    if has_pulp_plugin("core", min="3.23.0"):
        # Assert that filtering distributions by repository is possible
        distros = file_distribution_api_client.list(repository=repo.pulp_href).results
        assert len(distros) == 1

        distros = file_distribution_api_client.list(repository__in=[repo.pulp_href]).results
        assert len(distros) == 1

        # Assert that no results are returned when filtering by non-existent repository
        nonexistent_repository_href = f"{repo.pulp_href[:-37]}12345678-1234-1234-1234-012345678912/"
        distros = file_distribution_api_client.list(repository=nonexistent_repository_href).results
        assert len(distros) == 0
