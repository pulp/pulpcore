import pytest
import uuid

from collections import defaultdict

from pulpcore.client.pulp_file import RepositorySyncURL


@pytest.fixture
def perform_sync(
    file_bindings,
    file_repo,
    gen_object_with_cleanup,
    monitor_task,
):
    def _perform_sync(url, policy="immediate"):
        remote_data = {
            "url": str(url),
            "policy": policy,
            "name": str(uuid.uuid4()),
        }
        remote = gen_object_with_cleanup(file_bindings.RemotesFileApi, remote_data)

        body = RepositorySyncURL(remote=remote.pulp_href)
        monitor_task(file_bindings.RepositoriesFileApi.sync(file_repo.pulp_href, body).task)
        return file_repo

    yield _perform_sync


@pytest.mark.parallel
def test_bad_response_retry(bad_response_fixture_server, large_manifest_path, perform_sync):
    """
    Test downloader retrying after network failure during sync.
    """
    requests_record = bad_response_fixture_server.requests_record
    url = bad_response_fixture_server.make_url(large_manifest_path)

    perform_sync(url)

    # 1 for PULP_MANIFEST, and 4 for 1.iso
    assert len(requests_record) == 5
    assert "PULP_MANIFEST" in requests_record[0].raw_path
    for i in range(1, 5):
        assert "1.iso" in requests_record[i].raw_path


@pytest.mark.parallel
def test_bad_response_retry_multiple_files(
    bad_response_fixture_server,
    basic_manifest_path,
    perform_sync,
):
    """
    Test multiple file downloaders retrying after network failure during sync.
    """
    requests_record = bad_response_fixture_server.requests_record
    url = bad_response_fixture_server.make_url(basic_manifest_path)

    perform_sync(url)

    # 1 for PULP_MANIFEST, and 4 each for 1.iso, 2.iso, 3.iso
    assert len(requests_record) == 13
    records = defaultdict(int)
    for r in requests_record:
        filename = r.raw_path.split("/")[-1]
        records[filename] += 1

    assert records["PULP_MANIFEST"] == 1
    assert records["1.iso"] == 4
    assert records["2.iso"] == 4
    assert records["3.iso"] == 4
