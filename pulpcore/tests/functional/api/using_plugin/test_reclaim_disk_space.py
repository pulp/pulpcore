"""Tests that perform actions over reclaim disk space."""

import pytest

from urllib.parse import urljoin

from pulpcore.client.pulp_file import RepositorySyncURL

from pulpcore.tests.functional.utils import get_files_in_manifest, download_file


@pytest.mark.parallel
def test_reclaim_immediate_content(
    pulpcore_bindings,
    file_bindings,
    file_repo,
    file_remote_ssl_factory,
    basic_manifest_path,
    monitor_task,
):
    """
    Test whether immediate repository content can be reclaimed
    and then re-populated back after sync.
    """
    remote = file_remote_ssl_factory(manifest_path=basic_manifest_path, policy="immediate")

    # sync the repository with immediate policy
    repository_sync_data = RepositorySyncURL(remote=remote.pulp_href)
    sync_response = file_bindings.RepositoriesFileApi.sync(
        file_repo.pulp_href, repository_sync_data
    )
    monitor_task(sync_response.task)

    # reclaim disk space
    reclaim_response = pulpcore_bindings.RepositoriesReclaimSpaceApi.reclaim(
        {"repo_hrefs": [file_repo.pulp_href]}
    )
    monitor_task(reclaim_response.task)

    # assert no artifacts left
    expected_files = list(get_files_in_manifest(remote.url))
    for f in expected_files:
        artifacts = pulpcore_bindings.ArtifactsApi.list(sha256=f[1]).count
        assert artifacts == 0

    # sync repo again
    repository_sync_data = RepositorySyncURL(remote=remote.pulp_href)
    sync_response = file_bindings.RepositoriesFileApi.sync(
        file_repo.pulp_href, repository_sync_data
    )
    monitor_task(sync_response.task)

    # assert re-sync populated missing artifacts
    for f in expected_files:
        artifacts = pulpcore_bindings.ArtifactsApi.list(sha256=f[1]).count
        assert artifacts == 1


@pytest.fixture
def sync_repository_distribution(
    file_bindings,
    file_distribution_factory,
    file_remote_ssl_factory,
    file_repo_with_auto_publish,
    basic_manifest_path,
    monitor_task,
):
    def _sync_repository_distribution(policy="immediate"):
        remote = file_remote_ssl_factory(manifest_path=basic_manifest_path, policy=policy)

        repository_sync_data = RepositorySyncURL(remote=remote.pulp_href)
        sync_response = file_bindings.RepositoriesFileApi.sync(
            file_repo_with_auto_publish.pulp_href, repository_sync_data
        )
        monitor_task(sync_response.task)

        distribution = file_distribution_factory(repository=file_repo_with_auto_publish.pulp_href)

        return file_repo_with_auto_publish, remote, distribution

    return _sync_repository_distribution


@pytest.mark.parallel
def test_reclaim_on_demand_content(
    pulpcore_bindings,
    sync_repository_distribution,
    monitor_task,
):
    """
    Test whether on_demand repository content can be reclaimed
    and then re-populated back after client request.
    """
    repo, remote, distribution = sync_repository_distribution(policy="on_demand")

    content = get_files_in_manifest(urljoin(distribution.base_url, "PULP_MANIFEST")).pop()
    download_file(urljoin(distribution.base_url, content[0]))

    expected_files = get_files_in_manifest(remote.url)
    artifact_sha256 = get_file_by_path(content[0], expected_files)[1]
    assert 1 == pulpcore_bindings.ArtifactsApi.list(sha256=artifact_sha256).count

    # reclaim disk space
    reclaim_response = pulpcore_bindings.RepositoriesReclaimSpaceApi.reclaim(
        {"repo_hrefs": [repo.pulp_href]}
    )
    monitor_task(reclaim_response.task)

    assert 0 == pulpcore_bindings.ArtifactsApi.list(sha256=artifact_sha256).count

    download_file(urljoin(distribution.base_url, content[0]))

    assert 1 == pulpcore_bindings.ArtifactsApi.list(sha256=artifact_sha256).count


@pytest.mark.parallel
def test_immediate_reclaim_becomes_on_demand(
    pulpcore_bindings,
    sync_repository_distribution,
    monitor_task,
):
    """Tests if immediate content becomes like on_demand content after reclaim."""
    repo, remote, distribution = sync_repository_distribution()

    artifacts_before_reclaim = pulpcore_bindings.ArtifactsApi.list().count
    assert artifacts_before_reclaim > 0

    content = get_files_in_manifest(urljoin(distribution.base_url, "PULP_MANIFEST")).pop()
    # Populate cache
    download_file(urljoin(distribution.base_url, content[0]))

    reclaim_response = pulpcore_bindings.RepositoriesReclaimSpaceApi.reclaim(
        {"repo_hrefs": [repo.pulp_href]}
    )
    monitor_task(reclaim_response.task)

    expected_files = get_files_in_manifest(remote.url)
    artifact_sha256 = get_file_by_path(content[0], expected_files)[1]
    assert 0 == pulpcore_bindings.ArtifactsApi.list(sha256=artifact_sha256).count

    download_file(urljoin(distribution.base_url, content[0]))

    assert 1 == pulpcore_bindings.ArtifactsApi.list(sha256=artifact_sha256).count


def test_specified_all_repos(
    pulpcore_bindings,
    file_repository_factory,
    monitor_task,
):
    """Tests that specifying all repos w/ '*' properly grabs all the repos."""
    repos = [file_repository_factory().pulp_href.split("/")[-2] for _ in range(10)]

    reclaim_response = pulpcore_bindings.RepositoriesReclaimSpaceApi.reclaim({"repo_hrefs": ["*"]})
    task_status = monitor_task(reclaim_response.task)

    repos_locked = [
        r.split(":")[-1] for r in task_status.reserved_resources_record if "filerepository" in r
    ]
    assert len(repos) == len(repos_locked)
    assert set(repos) == set(repos_locked)


def get_file_by_path(path, files):
    try:
        return next(filter(lambda x: x[0] == path, files))
    except StopIteration:
        pytest.fail(f"Could not find a file with the path {path}")
