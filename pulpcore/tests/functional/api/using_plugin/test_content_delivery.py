"""Tests related to content delivery."""

import hashlib
import subprocess
import uuid
from urllib.parse import urljoin

import pytest
from aiohttp.client_exceptions import ClientPayloadError, ClientResponseError

from pulpcore.client.pulp_file import RepositorySyncURL
from pulpcore.tests.functional.utils import download_file, get_files_in_manifest


@pytest.mark.parallel
def test_delete_remote_on_demand(
    distribution_base_url,
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
    distribution_base_url = distribution_base_url(distribution.base_url)

    # Download the manifest from the remote
    expected_file_list = list(get_files_in_manifest(remote.url))

    # Delete the remote and assert that downloading content returns a 404
    monitor_task(file_bindings.RemotesFileApi.delete(remote.pulp_href).task)
    with pytest.raises(ClientResponseError) as exc:
        url = urljoin(distribution_base_url, expected_file_list[0][0])
        download_file(url)
    assert exc.value.status == 404

    # Recreate the remote and sync into the repository using it
    remote = file_remote_ssl_factory(manifest_path=basic_manifest_path, policy="on_demand")
    body = RepositorySyncURL(remote=remote.pulp_href)
    monitor_task(file_bindings.RepositoriesFileApi.sync(repo.pulp_href, body).task)

    # Assert that files can now be downloaded from the distribution
    content_unit_url = urljoin(distribution_base_url, expected_file_list[0][0])
    downloaded_file = download_file(content_unit_url)
    actual_checksum = hashlib.sha256(downloaded_file.body).hexdigest()
    expected_checksum = expected_file_list[0][1]
    assert expected_checksum == actual_checksum


@pytest.mark.parallel
def test_remote_artifact_url_update(
    distribution_base_url,
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
    distribution_base_url = distribution_base_url(distribution.base_url)

    # Download the manifest from the remote
    expected_file_list = list(get_files_in_manifest(remote.url))

    # Assert that trying to download content raises a 404
    with pytest.raises(ClientResponseError) as exc:
        url = urljoin(distribution_base_url, expected_file_list[0][0])
        download_file(url)
    assert exc.value.status == 404

    # Create a new remote that points to a repository that does have the missing content
    remote2 = file_remote_ssl_factory(manifest_path=basic_manifest_path, policy="on_demand")

    # Sync from the remote and assert that content can now be downloaded
    body = RepositorySyncURL(remote=remote2.pulp_href)
    monitor_task(
        file_bindings.RepositoriesFileApi.sync(file_repo_with_auto_publish.pulp_href, body).task
    )
    content_unit_url = urljoin(distribution_base_url, expected_file_list[0][0])
    downloaded_file = download_file(content_unit_url)
    actual_checksum = hashlib.sha256(downloaded_file.body).hexdigest()
    expected_checksum = expected_file_list[0][1]
    assert expected_checksum == actual_checksum


@pytest.mark.parallel
def test_remote_content_changed_with_on_demand(
    write_3_iso_file_fixture_data_factory,
    distribution_base_url,
    file_repo_with_auto_publish,
    file_remote_ssl_factory,
    file_bindings,
    monitor_task,
    file_distribution_factory,
    tmp_path,
):
    """
    GIVEN a remote synced on demand with fileA (e.g, digest=123),
    AND the remote server, fileA changed its content (e.g, digest=456),

    WHEN the client first requests that content
    THEN the content app will start a response but close the connection before finishing
    AND no file will be present in the filesystem

    WHEN the client requests that content again (within the RA cooldown interval)
    THEN the content app will return a 404
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
    write_3_iso_file_fixture_data_factory("basic", overwrite=True)

    get_url = urljoin(distribution_base_url(distribution.base_url), expected_file_list[0][0])

    # WHEN (first request)
    output_file = tmp_path / "out.rpm"
    cmd = ["curl", "-v", get_url, "-o", str(output_file)]
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    # THEN
    assert not output_file.exists()
    assert result.returncode == 18
    assert b"* Closing connection 0" in result.stderr
    assert b"curl: (18) transfer closed with outstanding read data remaining" in result.stderr

    # WHEN (second request)
    result = subprocess.run(["curl", "-v", get_url], stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    # THEN
    assert result.returncode == 0
    assert b"< HTTP/1.1 404 Not Found" in result.stderr


@pytest.mark.parallel
def test_handling_remote_artifact_on_demand_streaming_failure(
    write_3_iso_file_fixture_data_factory,
    distribution_base_url,
    file_repo_with_auto_publish,
    file_remote_factory,
    file_bindings,
    monitor_task,
    monitor_task_group,
    file_distribution_factory,
    gen_object_with_cleanup,
    generate_server_and_remote,
):
    """
    GIVEN A content synced with on-demand which has 2 RemoteArtifacts (Remote + ACS).
    AND Only the ACS RemoteArtifact (that has priority on the content-app) is corrupted

    WHEN a client requests the content for the first time
    THEN the client doesnt get any content

    WHEN a client requests the content for the second time
    THEN the client gets the right content
    """

    # Plumbing
    def create_simple_remote(manifest_path):
        remote = file_remote_factory(manifest_path=manifest_path, policy="on_demand")
        body = RepositorySyncURL(remote=remote.pulp_href)
        monitor_task(
            file_bindings.RepositoriesFileApi.sync(file_repo_with_auto_publish.pulp_href, body).task
        )
        return remote

    def create_acs_remote(manifest_path):
        acs_server, acs_remote = generate_server_and_remote(
            manifest_path=manifest_path, policy="on_demand"
        )
        acs = gen_object_with_cleanup(
            file_bindings.AcsFileApi,
            {"remote": acs_remote.pulp_href, "paths": [], "name": str(uuid.uuid4())},
        )
        monitor_task_group(file_bindings.AcsFileApi.refresh(acs.pulp_href).task_group)
        return acs

    def sync_publish_and_distribute(remote):
        body = RepositorySyncURL(remote=remote.pulp_href)
        monitor_task(
            file_bindings.RepositoriesFileApi.sync(file_repo_with_auto_publish.pulp_href, body).task
        )
        repo = file_bindings.RepositoriesFileApi.read(file_repo_with_auto_publish.pulp_href)
        distribution = file_distribution_factory(repository=repo.pulp_href)
        return distribution

    def get_original_content_info(remote):
        expected_files = get_files_in_manifest(remote.url)
        content_unit = list(expected_files)[0]
        return content_unit[0], content_unit[1]

    def download_from_distribution(content, distribution):
        content_unit_url = urljoin(distribution_base_url(distribution.base_url), content_name)
        downloaded_file = download_file(content_unit_url)
        actual_checksum = hashlib.sha256(downloaded_file.body).hexdigest()
        return actual_checksum

    # GIVEN
    basic_manifest_path = write_3_iso_file_fixture_data_factory("basic", seed=123)
    acs_manifest_path = write_3_iso_file_fixture_data_factory("acs", seed=123)
    remote = create_simple_remote(basic_manifest_path)
    distribution = sync_publish_and_distribute(remote)
    create_acs_remote(acs_manifest_path)
    write_3_iso_file_fixture_data_factory("acs", overwrite=True)  # corrupt

    # WHEN/THEN (first request)
    content_name, expected_checksum = get_original_content_info(remote)

    with pytest.raises(ClientPayloadError, match="Response payload is not completed"):
        download_from_distribution(content_name, distribution)

    # WHEN/THEN (second request)
    actual_checksum = download_from_distribution(content_name, distribution)
    assert actual_checksum == expected_checksum
