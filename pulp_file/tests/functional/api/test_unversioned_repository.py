"""Tests for repositories without repository versions."""

import hashlib
import uuid

import pytest
from aiohttp import ClientResponseError

from pulpcore.client.pulp_file import ApiException


@pytest.fixture
def unversioned_repo(file_repository_factory):
    return file_repository_factory(versioned=False)


@pytest.fixture
def download(http_get, distribution_base_url):
    def _download(distribution, path):
        return http_get(f"{distribution_base_url(distribution.base_url)}{path}")

    return _download


def _modify(file_bindings, monitor_task, repo, add=(), remove=()):
    body = {
        "add_content_units": [c.pulp_href for c in add],
        "remove_content_units": [c.pulp_href for c in remove],
    }
    return monitor_task(file_bindings.RepositoriesFileApi.modify(repo.pulp_href, body).task)


@pytest.mark.parallel
def test_create_unversioned_repository(file_bindings, unversioned_repo):
    """Verify that an unversioned repository has no versions and no `latest_version_href`."""
    assert unversioned_repo.versioned is False
    assert unversioned_repo.latest_version_href is None
    versions = file_bindings.RepositoriesFileVersionsApi.list(unversioned_repo.pulp_href)
    assert versions.count == 0


@pytest.mark.parallel
def test_add_serve_and_remove_content(
    file_bindings,
    unversioned_repo,
    file_distribution_factory,
    file_content_unit_with_name_factory,
    monitor_task,
    download,
):
    """
    Verify that added content is served right away and no longer served once removed, and that
    no version is created.
    """
    distribution = file_distribution_factory(repository=unversioned_repo.pulp_href)
    path = str(uuid.uuid4())
    content = file_content_unit_with_name_factory(path)

    task = _modify(file_bindings, monitor_task, unversioned_repo, add=[content])
    assert task.created_resources == []
    versions = file_bindings.RepositoriesFileVersionsApi.list(unversioned_repo.pulp_href)
    assert versions.count == 0
    assert hashlib.sha256(download(distribution, path)).hexdigest() == content.sha256

    _modify(file_bindings, monitor_task, unversioned_repo, remove=[content])
    with pytest.raises(ClientResponseError) as exc:
        download(distribution, path)
    assert exc.value.status == 404


@pytest.mark.parallel
def test_same_relative_path_replaces_content(
    file_bindings,
    unversioned_repo,
    file_distribution_factory,
    file_content_unit_with_name_factory,
    monitor_task,
    download,
):
    """Verify that adding content with the same relative path replaces the existing content."""
    distribution = file_distribution_factory(repository=unversioned_repo.pulp_href)
    path = str(uuid.uuid4())
    first = file_content_unit_with_name_factory(path)
    second = file_content_unit_with_name_factory(path)

    _modify(file_bindings, monitor_task, unversioned_repo, add=[first])
    _modify(file_bindings, monitor_task, unversioned_repo, add=[second])

    assert hashlib.sha256(download(distribution, path)).hexdigest() == second.sha256


@pytest.mark.parallel
def test_unversioned_restrictions(file_bindings, file_repository_factory, unversioned_repo):
    """
    Verify that unversioned repositories reject `autopublish`, a change of `versioned` and
    publications.
    """
    with pytest.raises(ApiException) as exc:
        file_repository_factory(versioned=False, autopublish=True)
    assert exc.value.status == 400

    with pytest.raises(ApiException) as exc:
        file_bindings.RepositoriesFileApi.partial_update(
            unversioned_repo.pulp_href, {"versioned": True}
        )
    assert exc.value.status == 400

    with pytest.raises(ApiException) as exc:
        file_bindings.PublicationsFileApi.create({"repository": unversioned_repo.pulp_href})
    assert exc.value.status == 400
