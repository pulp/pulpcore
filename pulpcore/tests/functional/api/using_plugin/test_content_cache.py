"""Tests related to content cache."""

import pytest
from urllib.parse import urljoin

from pulpcore.client.pulp_file import (
    RepositoryAddRemoveContent,
    RepositorySyncURL,
    FileFilePublication,
    PatchedfileFileDistribution,
)

from pulpcore.tests.functional.utils import get_from_url


@pytest.mark.parallel
def test_full_workflow(
    file_repo_with_auto_publish,
    basic_manifest_path,
    file_remote_factory,
    file_bindings,
    file_distribution_factory,
    monitor_task,
    redis_status,
    pulp_content_url,
):
    if not redis_status:
        pytest.xfail("Could not connect to the Redis server")

    def _check_cache(url):
        """Helper to check if cache miss or hit"""
        r = get_from_url(url)
        if r.history:
            r = r.history[0]
            return 200 if r.status == 302 else r.status, r.headers.get("X-PULP-CACHE")
        return r.status, r.headers.get("X-PULP-CACHE")

    # Sync from the remote and assert that a new repository version is created
    remote = file_remote_factory(manifest_path=basic_manifest_path, policy="immediate")
    body = RepositorySyncURL(remote=remote.pulp_href)
    monitor_task(
        file_bindings.RepositoriesFileApi.sync(file_repo_with_auto_publish.pulp_href, body).task
    )
    repo = file_bindings.RepositoriesFileApi.read(file_repo_with_auto_publish.pulp_href)
    assert repo.latest_version_href.endswith("/versions/1/")

    body = FileFilePublication(repository=repo.pulp_href)
    pub2 = file_bindings.PublicationsFileApi.read(
        monitor_task(file_bindings.PublicationsFileApi.create(body).task).created_resources[0]
    )
    distro = file_distribution_factory(repository=repo.pulp_href)

    # Checks responses are cached for content
    files = ["", "", "PULP_MANIFEST", "PULP_MANIFEST", "1.iso", "1.iso"]
    for i, file in enumerate(files):
        url = urljoin(distro.base_url, file)
        assert (200, "HIT" if i % 2 == 1 else "MISS") == _check_cache(url), file

    # Check that removing the repository from the distribution invalidates the cache
    body = PatchedfileFileDistribution(repository="")
    monitor_task(file_bindings.DistributionsFileApi.partial_update(distro.pulp_href, body).task)
    files = ["", "PULP_MANIFEST", "1.iso"]
    for file in files:
        url = urljoin(distro.base_url, file)
        assert (404, None) == _check_cache(url), file

    # Check that responses are cacheable after a repository is added back
    body = PatchedfileFileDistribution(repository=repo.pulp_href)
    monitor_task(file_bindings.DistributionsFileApi.partial_update(distro.pulp_href, body).task)
    files = ["", "", "PULP_MANIFEST", "PULP_MANIFEST", "1.iso", "1.iso"]
    for i, file in enumerate(files):
        url = urljoin(distro.base_url, file)
        assert (200, "HIT" if i % 2 == 1 else "MISS") == _check_cache(url), file

    # Add a new distribution and check that its responses are cached separately
    distro2 = file_distribution_factory(repository=repo.pulp_href)
    url = urljoin(pulp_content_url, f"{distro2.base_path}/")
    files = ["", "", "PULP_MANIFEST", "PULP_MANIFEST", "1.iso", "1.iso"]
    for i, file in enumerate(files):
        url = urljoin(distro2.base_url, file)
        assert (200, "HIT" if i % 2 == 1 else "MISS") == _check_cache(url), file

    # Test that updating a repository pointed by multiple distributions invalidates all
    cfile = file_bindings.ContentFilesApi.list(
        relative_path="1.iso", repository_version=repo.latest_version_href
    ).results[0]
    body = RepositoryAddRemoveContent(remove_content_units=[cfile.pulp_href])
    response = monitor_task(file_bindings.RepositoriesFileApi.modify(repo.pulp_href, body).task)
    pub3 = file_bindings.PublicationsFileApi.read(response.created_resources[1])
    files = ["", "", "PULP_MANIFEST", "PULP_MANIFEST", "2.iso", "2.iso"]
    for i, file in enumerate(files):
        url = urljoin(distro.base_url, file)
        assert (200, "HIT" if i % 2 == 1 else "MISS") == _check_cache(url), file
        url = urljoin(distro2.base_url, file)
        assert (200, "HIT" if i % 2 == 1 else "MISS") == _check_cache(url), file

    # Tests that deleting one distribution sharing a repository only invalidates its cache
    monitor_task(file_bindings.DistributionsFileApi.delete(distro2.pulp_href).task)
    files = ["", "PULP_MANIFEST", "2.iso"]
    for file in files:
        url = urljoin(distro.base_url, file)
        assert (200, "HIT") == _check_cache(url), file
        url = urljoin(distro2.base_url, file)
        assert (404, None) == _check_cache(url), file

    # Test that deleting a publication not being served doesn't invalidate cache
    file_bindings.PublicationsFileApi.delete(pub2.pulp_href)
    files = ["", "PULP_MANIFEST", "2.iso"]
    for file in files:
        url = urljoin(distro.base_url, file)
        assert (200, "HIT") == _check_cache(url), file

    # Test that deleting the serving publication does invalidate the cache"""
    # Reverts back to serving self.pub1
    file_bindings.PublicationsFileApi.delete(pub3.pulp_href)
    files = ["", "", "PULP_MANIFEST", "PULP_MANIFEST", "2.iso", "2.iso"]
    for i, file in enumerate(files):
        url = urljoin(distro.base_url, file)
        assert (200, "HIT" if i % 2 == 1 else "MISS") == _check_cache(url), file

    # Tests that deleting a repository invalidates the cache"""
    monitor_task(file_bindings.RepositoriesFileApi.delete(repo.pulp_href).task)
    files = ["", "PULP_MANIFEST", "2.iso"]
    for file in files:
        url = urljoin(distro.base_url, file)
        assert (404, None) == _check_cache(url), file

    # Tests that accessing a file that doesn't exist on content app gives 404
    files = ["invalid", "another/bad-one", "DNE/"]
    for file in files:
        url = urljoin(pulp_content_url, file)
        assert (404, None) == _check_cache(url), file
