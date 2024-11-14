"""Tests related to content delivery."""

from aiohttp.client_exceptions import ClientResponseError, ClientPayloadError
import hashlib
import pytest
import subprocess
from urllib.parse import urljoin

from pulpcore.client.pulp_file import (
    RepositorySyncURL,
)

from pulpcore.tests.functional.utils import download_file, get_files_in_manifest


@pytest.mark.parallel
def test_delete_remote_on_demand(
    file_repo_with_auto_publish,
    file_remote_ssl_factory,
    file_bindings,
    basic_manifest_path,
    monitor_task,
    file_distribution_factory,
):
    # Create a remote with on_demand download policy
    remote = file_remote_ssl_factory(manifest_path=basic_manifest_path, policy="on_demand")

    # Sync from the remote
    body = RepositorySyncURL(remote=remote.pulp_href)
    monitor_task(
        file_bindings.RepositoriesFileApi.sync(file_repo_with_auto_publish.pulp_href, body).task
    )
    repo = file_bindings.RepositoriesFileApi.read(file_repo_with_auto_publish.pulp_href)

    # Create a distribution pointing to the repository
    distribution = file_distribution_factory(repository=repo.pulp_href)

    # Download the manifest from the remote
    expected_file_list = list(get_files_in_manifest(remote.url))

    # Delete the remote and assert that downloading content returns a 404
    monitor_task(file_bindings.RemotesFileApi.delete(remote.pulp_href).task)
    with pytest.raises(ClientResponseError) as exc:
        url = urljoin(distribution.base_url, expected_file_list[0][0])
        download_file(url)
    assert exc.value.status == 404

    # Recreate the remote and sync into the repository using it
    remote = file_remote_ssl_factory(manifest_path=basic_manifest_path, policy="on_demand")
    body = RepositorySyncURL(remote=remote.pulp_href)
    monitor_task(file_bindings.RepositoriesFileApi.sync(repo.pulp_href, body).task)

    # Assert that files can now be downloaded from the distribution
    content_unit_url = urljoin(distribution.base_url, expected_file_list[0][0])
    downloaded_file = download_file(content_unit_url)
    actual_checksum = hashlib.sha256(downloaded_file.body).hexdigest()
    expected_checksum = expected_file_list[0][1]
    assert expected_checksum == actual_checksum


@pytest.mark.parallel
def test_remote_artifact_url_update(
    file_repo_with_auto_publish,
    file_remote_ssl_factory,
    file_bindings,
    basic_manifest_path,
    basic_manifest_only_path,
    monitor_task,
    file_distribution_factory,
):
    # Create a remote that points to a repository that only has the manifest, but no content
    remote = file_remote_ssl_factory(manifest_path=basic_manifest_only_path, policy="on_demand")

    # Sync from the remote
    body = RepositorySyncURL(remote=remote.pulp_href)
    monitor_task(
        file_bindings.RepositoriesFileApi.sync(file_repo_with_auto_publish.pulp_href, body).task
    )
    repo = file_bindings.RepositoriesFileApi.read(file_repo_with_auto_publish.pulp_href)

    # Create a distribution from the publication
    distribution = file_distribution_factory(repository=repo.pulp_href)

    # Download the manifest from the remote
    expected_file_list = list(get_files_in_manifest(remote.url))

    # Assert that trying to download content raises a 404
    with pytest.raises(ClientResponseError) as exc:
        url = urljoin(distribution.base_url, expected_file_list[0][0])
        download_file(url)
    assert exc.value.status == 404

    # Create a new remote that points to a repository that does have the missing content
    remote2 = file_remote_ssl_factory(manifest_path=basic_manifest_path, policy="on_demand")

    # Sync from the remote and assert that content can now be downloaded
    body = RepositorySyncURL(remote=remote2.pulp_href)
    monitor_task(
        file_bindings.RepositoriesFileApi.sync(file_repo_with_auto_publish.pulp_href, body).task
    )
    content_unit_url = urljoin(distribution.base_url, expected_file_list[0][0])
    downloaded_file = download_file(content_unit_url)
    actual_checksum = hashlib.sha256(downloaded_file.body).hexdigest()
    expected_checksum = expected_file_list[0][1]
    assert expected_checksum == actual_checksum


@pytest.mark.parallel
def test_remote_content_changed_with_on_demand(
    write_3_iso_file_fixture_data_factory,
    file_repo_with_auto_publish,
    file_remote_ssl_factory,
    file_bindings,
    monitor_task,
    file_distribution_factory,
):
    """
    GIVEN a remote synced on demand with fileA (e.g, digest=123),
    WHEN on the remote server, fileA changed its content (e.g, digest=456),
    THEN retrieving fileA from the content app will cause a connection-close/incomplete-response.
    """
    # GIVEN
    basic_manifest_path = write_3_iso_file_fixture_data_factory("basic")
    remote = file_remote_ssl_factory(manifest_path=basic_manifest_path, policy="on_demand")
    body = RepositorySyncURL(remote=remote.pulp_href)
    monitor_task(
        file_bindings.RepositoriesFileApi.sync(file_repo_with_auto_publish.pulp_href, body).task
    )
    repo = file_bindings.RepositoriesFileApi.read(file_repo_with_auto_publish.pulp_href)
    distribution = file_distribution_factory(repository=repo.pulp_href)
    expected_file_list = list(get_files_in_manifest(remote.url))

    # WHEN
    write_3_iso_file_fixture_data_factory("basic", overwrite=True)

    # THEN
    get_url = urljoin(distribution.base_url, expected_file_list[0][0])
    with pytest.raises(ClientPayloadError, match="Response payload is not completed"):
        download_file(get_url)

    # Assert again with curl just to be sure.
    result = subprocess.run(["curl", "-v", get_url], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    assert result.returncode == 18
    assert b"* Closing connection 0" in result.stderr
    assert b"curl: (18) transfer closed with outstanding read data remaining" in result.stderr
