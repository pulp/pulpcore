"""Tests that sync file plugin repositories."""

import os
import uuid

import pytest

from urllib.parse import urljoin

from pulpcore.tests.functional.utils import PulpTaskError

from pulpcore.client.pulp_file import RepositorySyncURL


def test_sync_file_protocol_handler(
    file_bindings,
    file_repo,
    gen_object_with_cleanup,
    monitor_task,
    fixtures_cfg,
    wget_recursive_download_on_host,
):
    """Test syncing from a file repository with the file:// protocol handler"""
    wget_recursive_download_on_host(urljoin(fixtures_cfg.remote_fixtures_origin, "file/"), "/tmp")
    remote_kwargs = {
        "url": "file:///tmp/file/PULP_MANIFEST",
        "policy": "immediate",
        "name": str(uuid.uuid4()),
    }
    remote = gen_object_with_cleanup(file_bindings.RemotesFileApi, remote_kwargs)
    files = set(os.listdir("/tmp/file/"))

    body = RepositorySyncURL(remote=remote.pulp_href)
    monitor_task(file_bindings.RepositoriesFileApi.sync(file_repo.pulp_href, body).task)

    # test that all the files are still present
    assert set(os.listdir("/tmp/file/")) == files

    file_repo = file_bindings.RepositoriesFileApi.read(file_repo.pulp_href)
    assert file_repo.latest_version_href.endswith("/versions/1/")

    version = file_bindings.RepositoriesFileVersionsApi.read(file_repo.latest_version_href)
    assert version.content_summary.present["file.file"]["count"] == 3
    assert version.content_summary.added["file.file"]["count"] == 3


@pytest.mark.parallel
def test_mirrored_sync(
    file_bindings,
    file_repo,
    file_remote_ssl_factory,
    basic_manifest_path,
    monitor_task,
):
    """Assert that syncing the repository w/ mirror=True creates a publication."""
    remote = file_remote_ssl_factory(manifest_path=basic_manifest_path, policy="on_demand")

    repository_sync_data = RepositorySyncURL(remote=remote.pulp_href, mirror=True)
    sync_response = file_bindings.RepositoriesFileApi.sync(
        file_repo.pulp_href, repository_sync_data
    )
    task = monitor_task(sync_response.task)

    # Check that all the appropriate resources were created
    assert len(task.created_resources) == 2
    assert any(["publication" in resource for resource in task.created_resources])
    assert any(["version" in resource for resource in task.created_resources])


@pytest.mark.parallel
def test_invalid_url(file_bindings, file_repo, gen_object_with_cleanup, monitor_task):
    """Sync a repository using a remote url that does not exist."""
    remote_kwargs = {
        "url": "http://i-am-an-invalid-url.com/invalid/",
        "policy": "immediate",
        "name": str(uuid.uuid4()),
    }
    remote = gen_object_with_cleanup(file_bindings.RemotesFileApi, remote_kwargs)

    body = RepositorySyncURL(remote=remote.pulp_href)
    with pytest.raises(PulpTaskError):
        monitor_task(file_bindings.RepositoriesFileApi.sync(file_repo.pulp_href, body).task)


@pytest.mark.parallel
def test_invalid_file(
    file_repo, file_bindings, invalid_manifest_path, file_remote_factory, monitor_task
):
    """Sync a repository using an invalid file repository."""
    remote = file_remote_factory(manifest_path=invalid_manifest_path, policy="immediate")
    body = RepositorySyncURL(remote=remote.pulp_href)
    with pytest.raises(PulpTaskError):
        monitor_task(file_bindings.RepositoriesFileApi.sync(file_repo.pulp_href, body).task)


@pytest.mark.parallel
def test_duplicate_file_sync(
    file_bindings,
    file_repo,
    file_remote_factory,
    duplicate_filename_paths,
    monitor_task,
):
    remote = file_remote_factory(manifest_path=duplicate_filename_paths[0], policy="on_demand")
    remote2 = file_remote_factory(manifest_path=duplicate_filename_paths[1], policy="on_demand")

    body = RepositorySyncURL(remote=remote.pulp_href)
    monitor_task(file_bindings.RepositoriesFileApi.sync(file_repo.pulp_href, body).task)
    file_repo = file_bindings.RepositoriesFileApi.read(file_repo.pulp_href)

    version = file_bindings.RepositoriesFileVersionsApi.read(file_repo.latest_version_href)
    assert version.content_summary.present["file.file"]["count"] == 3
    assert version.content_summary.added["file.file"]["count"] == 3
    assert file_repo.latest_version_href.endswith("/1/")

    body = RepositorySyncURL(remote=remote2.pulp_href)
    monitor_task(file_bindings.RepositoriesFileApi.sync(file_repo.pulp_href, body).task)
    file_repo = file_bindings.RepositoriesFileApi.read(file_repo.pulp_href)

    version = file_bindings.RepositoriesFileVersionsApi.read(file_repo.latest_version_href)
    assert version.content_summary.present["file.file"]["count"] == 3
    assert version.content_summary.added["file.file"]["count"] == 3
    assert file_repo.latest_version_href.endswith("/2/")


@pytest.mark.parallel
def test_filepath_includes_commas(
    file_bindings,
    file_repo,
    file_remote_factory,
    manifest_path_with_commas,
    monitor_task,
):
    """Sync a repository using a manifest file with a file whose relative_path includes commas"""
    remote = file_remote_factory(manifest_path=manifest_path_with_commas, policy="on_demand")

    body = RepositorySyncURL(remote=remote.pulp_href)
    monitor_task(file_bindings.RepositoriesFileApi.sync(file_repo.pulp_href, body).task)
    file_repo = file_bindings.RepositoriesFileApi.read(file_repo.pulp_href)

    version = file_bindings.RepositoriesFileVersionsApi.read(file_repo.latest_version_href)
    assert version.content_summary.present["file.file"]["count"] == 3
    assert version.content_summary.added["file.file"]["count"] == 3
    assert file_repo.latest_version_href.endswith("/1/")
