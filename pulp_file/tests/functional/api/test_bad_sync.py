from collections import defaultdict

import pytest
import uuid
import aiofiles
from aiohttp import web

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


@pytest.fixture(scope="class")
def gen_bad_response_fixture_server(gen_threaded_aiohttp_server):
    """
    This server will perform 3 bad responses for each file requested.

    1st response will be incomplete, sending only half of the data.
    2nd response will have corrupted data, with one byte changed.
    3rd response will return error 429.
    4th response will be correct.
    """

    def _gen_fixture_server(fixtures_root, ssl_ctx):
        record = []
        num_requests = defaultdict(int)

        async def handler(request):
            nonlocal num_requests
            record.append(request)
            relative_path = request.raw_path[1:]  # Strip off leading "/"
            file_path = fixtures_root / relative_path
            # Max retries is 3. So on fourth request, send full data
            num_requests[relative_path] += 1
            if "PULP_MANIFEST" in relative_path or num_requests[relative_path] % 4 == 0:
                return web.FileResponse(file_path)

            # On third request send 429 error, TooManyRequests
            if num_requests[relative_path] % 4 == 3:
                raise web.HTTPTooManyRequests

            size = file_path.stat().st_size
            response = web.StreamResponse(headers={"content-length": f"{size}"})
            await response.prepare(request)
            async with aiofiles.open(file_path, "rb") as f:
                # Send only partial content causing aiohttp.ClientPayloadError if request num == 1
                chunk = await f.read(size // 2)
                await response.write(chunk)
                # Send last chunk with modified last byte if request num == 2
                if num_requests[relative_path] % 4 == 2:
                    chunk2 = await f.read()
                    await response.write(chunk2[:-1])
                    await response.write(bytes([chunk2[-1] ^ 1]))
                else:
                    request.transport.close()

            return response

        app = web.Application()
        app.add_routes([web.get("/{tail:.*}", handler)])
        return gen_threaded_aiohttp_server(app, ssl_ctx, record)

    return _gen_fixture_server


@pytest.fixture(scope="class")
def bad_response_fixture_server(file_fixtures_root, gen_bad_response_fixture_server):
    return gen_bad_response_fixture_server(file_fixtures_root, None)


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
