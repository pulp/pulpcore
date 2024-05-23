"""Tests for Pulp`s download policies."""

from aiohttp.client_exceptions import ClientResponseError
from bs4 import BeautifulSoup
import hashlib
import os
import pytest
import subprocess
import uuid
from urllib.parse import urljoin

from pulpcore.tests.functional.utils import get_files_in_manifest, download_file

from pulpcore.app import settings
from pulpcore.client.pulp_file import FileFilePublication, RepositorySyncURL


OBJECT_STORAGES = (
    "storages.backends.s3boto3.S3Boto3Storage",
    "storages.backends.azure_storage.AzureStorage",
)


def _do_range_request_download_and_assert(url, range_header, expected_bytes):
    file1 = download_file(url, headers=range_header)
    file2 = download_file(url, headers=range_header)
    assert expected_bytes == len(file1.body)
    assert expected_bytes == len(file2.body)
    assert file1.body == file2.body

    assert file1.response_obj.status == 206
    assert file1.response_obj.status == file2.response_obj.status

    assert str(expected_bytes) == file1.response_obj.headers["Content-Length"]
    assert str(expected_bytes) == file2.response_obj.headers["Content-Length"]

    assert (
        file1.response_obj.headers["Content-Range"] == file2.response_obj.headers["Content-Range"]
    )


@pytest.mark.parallel
@pytest.mark.parametrize("download_policy", ["immediate", "on_demand", "streamed"])
def test_download_policy(
    pulpcore_bindings,
    file_bindings,
    file_repo,
    file_remote_ssl_factory,
    range_header_manifest_path,
    gen_object_with_cleanup,
    monitor_task,
    pulp_settings,
    has_pulp_plugin,
    download_policy,
):
    """Test that "on_demand" and "streamed" download policies work as expected."""
    if download_policy == "on_demand" and "SFTP" in pulp_settings.DEFAULT_FILE_STORAGE:
        pytest.skip("This storage technology is not properly supported.")

    remote = file_remote_ssl_factory(
        manifest_path=range_header_manifest_path, policy=download_policy
    )
    file_repo = file_bindings.RepositoriesFileApi.read(file_repo.pulp_href)
    assert file_repo.latest_version_href.endswith("/versions/0/")

    # Check what content and artifacts are in the fixture repository
    expected_files = get_files_in_manifest(remote.url)

    # Sync from the remote and assert that a new repository version is created
    body = RepositorySyncURL(remote=remote.pulp_href)
    monitor_task(file_bindings.RepositoriesFileApi.sync(file_repo.pulp_href, body).task)
    file_repo = file_bindings.RepositoriesFileApi.read(file_repo.pulp_href)
    assert file_repo.latest_version_href.endswith("/versions/1/")

    version = file_bindings.RepositoriesFileVersionsApi.read(file_repo.latest_version_href)
    assert version.content_summary.present["file.file"]["count"] == len(expected_files)
    assert version.content_summary.added["file.file"]["count"] == len(expected_files)

    # Sync again and assert that nothing changes
    latest_version_href = file_repo.latest_version_href
    monitor_task(file_bindings.RepositoriesFileApi.sync(file_repo.pulp_href, body).task)
    file_repo = file_bindings.RepositoriesFileApi.read(file_repo.pulp_href)
    assert latest_version_href == file_repo.latest_version_href

    version = file_bindings.RepositoriesFileVersionsApi.read(file_repo.latest_version_href)
    assert version.content_summary.present["file.file"]["count"] == len(expected_files)

    # Assert that no HTTP error was raised when list on_demand content
    content = file_bindings.ContentFilesApi.list(
        repository_version=file_repo.latest_version_href
    ).to_dict()["results"]
    assert len(content) == len(expected_files)

    # Create a Distribution
    distribution = gen_object_with_cleanup(
        file_bindings.DistributionsFileApi,
        {
            "name": str(uuid.uuid4()),
            "base_path": str(uuid.uuid4()),
            "repository": file_repo.pulp_href,
        },
    )

    # Assert that un-published content is not available
    for expected_file in expected_files:
        with pytest.raises(ClientResponseError) as exc:
            content_unit_url = urljoin(distribution.base_url, expected_file[0])
            download_file(content_unit_url)
        assert exc.value.status == 404

    # Create a File Publication and assert that the repository_version is set on the Publication.
    publish_data = FileFilePublication(repository=file_repo.pulp_href)
    publication = gen_object_with_cleanup(file_bindings.PublicationsFileApi, publish_data)
    assert publication.repository_version is not None

    # Assert that the dates on the distribution listing page represent the date that the content
    # was created in Pulp
    repo_uuid = file_repo.pulp_href.split("/")[-2]
    commands = (
        "from pulpcore.app.models import RepositoryContent;"
        "from pulp_file.app.models import FileContent;"
        "content = FileContent.objects.filter(relative_path='foo/0.iso');"
        f"rc = RepositoryContent.objects.filter(repository='{repo_uuid}', content__in=content);"
        "print(rc[0].pulp_created.strftime('%d-%b-%Y %H:%M'));"
    )
    process = subprocess.run(["pulpcore-manager", "shell", "-c", commands], capture_output=True)
    assert process.returncode == 0
    content_artifact_created_date = process.stdout.decode().strip()
    # Download the listing page for the 'foo' directory
    distribution_html_page = download_file(f"{distribution.base_url}foo")
    # Assert that requesting a path inside a distribution without a trailing / returns a 301
    assert distribution_html_page.response_obj.history[0].status == 301
    soup = BeautifulSoup(distribution_html_page.body, "html.parser")
    all_strings = [s for s in soup.strings if s != "\n"]
    assert all_strings[3] == "0.iso"
    content_properties_string = all_strings[4].strip()
    if has_pulp_plugin("core", min="3.24.0.dev"):
        assert "4.2 MB" in content_properties_string
    assert content_artifact_created_date in content_properties_string

    # Download one of the files and assert that it has the right checksum
    expected_files_list = list(expected_files)
    content_unit = expected_files_list[0]
    content_unit_url = urljoin(distribution.base_url, content_unit[0])
    downloaded_file = download_file(content_unit_url)
    actual_checksum = hashlib.sha256(downloaded_file.body).hexdigest()
    expected_checksum = content_unit[1]
    assert expected_checksum == actual_checksum
    if (
        download_policy == "immediate"
        and settings.DEFAULT_FILE_STORAGE != "pulpcore.app.models.storage.FileSystem"
        and settings.REDIRECT_TO_OBJECT_STORAGE
    ):
        content_disposition = downloaded_file.response_obj.headers.get("Content-Disposition")
        assert content_disposition is not None
        filename = os.path.basename(content_unit[0])
        assert f"attachment;filename={filename}" == content_disposition

    # Assert proper download with range requests smaller than one chunk of downloader
    range_header = {"Range": "bytes=1048586-1049586"}
    num_bytes = 1001
    content_unit = expected_files_list[1]
    content_unit_url = urljoin(distribution.base_url, content_unit[0])
    _do_range_request_download_and_assert(content_unit_url, range_header, num_bytes)

    # Assert proper download with range requests spanning multiple chunks of downloader
    range_header = {"Range": "bytes=1048176-2248576"}
    num_bytes = 1200401
    content_unit = expected_files_list[2]
    content_unit_url = urljoin(distribution.base_url, content_unit[0])
    _do_range_request_download_and_assert(content_unit_url, range_header, num_bytes)

    # Assert that multiple requests with different Range header values work as expected
    range_header = {"Range": "bytes=1048176-2248576"}
    num_bytes = 1200401
    content_unit = expected_files_list[3]
    content_unit_url = urljoin(distribution.base_url, content_unit[0])
    _do_range_request_download_and_assert(content_unit_url, range_header, num_bytes)

    range_header = {"Range": "bytes=2042176-3248576"}
    num_bytes = 1206401
    content_unit = expected_files_list[3]
    content_unit_url = urljoin(distribution.base_url, content_unit[0])
    _do_range_request_download_and_assert(content_unit_url, range_header, num_bytes)

    # Assert that range requests with a negative start value errors as expected
    content_unit = expected_files_list[4]
    content_unit_url = urljoin(distribution.base_url, content_unit[0])
    # The S3 test API project doesn't handle invalid Range values correctly
    if settings.DEFAULT_FILE_STORAGE == "pulpcore.app.models.storage.FileSystem":
        with pytest.raises(ClientResponseError) as exc:
            range_header = {"Range": "bytes=-1-11"}
            download_file(content_unit_url, headers=range_header)
        assert exc.value.status == 416

    # Assert that a range request with a start value larger than the content errors
    content_unit = expected_files_list[5]
    content_unit_url = urljoin(distribution.base_url, content_unit[0])
    with pytest.raises(ClientResponseError) as exc:
        range_header = {"Range": "bytes=10485860-10485870"}
        download_file(content_unit_url, headers=range_header)
    assert exc.value.status == 416

    # Assert that a range request with an end value that is larger than the data works
    range_header = {"Range": "bytes=4193804-4294304"}
    num_bytes = 500
    content_unit = expected_files_list[6]
    content_unit_url = urljoin(distribution.base_url, content_unit[0])
    _do_range_request_download_and_assert(content_unit_url, range_header, num_bytes)

    # Assert that artifacts were not downloaded if policy is not immediate
    if download_policy != "immediate":
        # Assert that artifacts were not downloaded
        content_unit = expected_files_list[7]
        assert pulpcore_bindings.ArtifactsApi.list(sha256=content_unit[1]).results == []

        # Assert that an artifact was saved for the "on_demand" policy and not saved for the
        # "streamed" policy. Only check the first content unit because Range requests don't
        # cause the artifact to be saved. https://github.com/pulp/pulpcore/issues/3060
        content_unit = expected_files_list[0]
        if download_policy == "on_demand":
            assert len(pulpcore_bindings.ArtifactsApi.list(sha256=content_unit[1]).results) == 1
        else:
            assert len(pulpcore_bindings.ArtifactsApi.list(sha256=content_unit[1]).results) == 0

        # Change download policy to immediate
        response = file_bindings.RemotesFileApi.partial_update(
            remote.pulp_href, {"policy": "immediate"}
        )
        monitor_task(response.task)
        remote = file_bindings.RemotesFileApi.read(remote.pulp_href)
        assert remote.policy == "immediate"

        # Sync from the remote and assert that artifacts are downloaded
        monitor_task(file_bindings.RepositoriesFileApi.sync(file_repo.pulp_href, body).task)
        for f in expected_files:
            assert len(pulpcore_bindings.ArtifactsApi.list(sha256=f[1]).results) == 1
