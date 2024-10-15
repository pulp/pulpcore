import pytest
import uuid
import hashlib

from unittest.mock import Mock, AsyncMock
from aiohttp.test_utils import make_mocked_request, TestClient, TestServer
from asgiref.sync import sync_to_async

from pulpcore.content import Handler, server
from pulpcore.plugin.models import (
    Artifact,
    Content,
    ContentArtifact,
    Distribution,
    Remote,
    RemoteArtifact,
)


@pytest.fixture
def download_result_mock(tmp_path):
    dr = Mock()
    dr.artifact_attributes = {"size": 0}
    for digest_type in Artifact.DIGEST_FIELDS:
        dr.artifact_attributes[digest_type] = "abc123"
    tmp_file = tmp_path / str(uuid.uuid4())
    tmp_file.write_text("abc123")
    dr.path = str(tmp_file)
    return dr


@pytest.fixture
def c1(db):
    return Content.objects.create()


@pytest.fixture
def ca1(c1):
    return ContentArtifact.objects.create(artifact=None, content=c1, relative_path="c1")


@pytest.fixture
def ra1(ca1):
    return Mock(content_artifact=ca1)


@pytest.fixture
def c2(db):
    return Content.objects.create()


@pytest.fixture
def ca2(c2):
    return ContentArtifact.objects.create(artifact=None, content=c2, relative_path="c1")


@pytest.fixture
def ra2(ca2):
    return Mock(content_artifact=ca2)


def test_save_artifact(c1, ra1, download_result_mock):
    """Artifact needs to be created."""
    handler = Handler()
    new_artifact = handler._save_artifact(download_result_mock, ra1)
    c1 = Content.objects.get(pk=c1.pk)
    assert new_artifact is not None
    assert c1._artifacts.get().pk == new_artifact.pk


def test_save_artifact_artifact_already_exists(c2, ra1, ra2, download_result_mock):
    """Artifact turns out to already exist."""
    cch = Handler()
    new_artifact = cch._save_artifact(download_result_mock, ra1)

    existing_artifact = cch._save_artifact(download_result_mock, ra2)
    c2 = Content.objects.get(pk=c2.pk)
    assert existing_artifact.pk == new_artifact.pk
    assert c2._artifacts.get().pk == existing_artifact.pk


# Test pull through features
@pytest.fixture
def remote123(db):
    return Remote.objects.create(name="123", url="https://123")


@pytest.fixture
def request123():
    return Mock(match_info={"path": "c123"})


# pytest-django fixtures does not work when testing async code
async def create_artifact(tmp_path):
    tmp_file = tmp_path / str(uuid.uuid4())
    tmp_file.write_text(str(tmp_file))
    artifact = Artifact.init_and_validate(str(tmp_file))
    await artifact.asave()
    return artifact


async def create_content():
    return await Content.objects.acreate()


async def create_content_artifact(content):
    return await ContentArtifact.objects.acreate(
        artifact=None, content=content, relative_path="c123"
    )


async def create_remote(url="https://123"):
    return await Remote.objects.acreate(name=str(uuid.uuid4()), url=url)


async def create_remote_artifact(remote, ca):
    return await RemoteArtifact.objects.acreate(
        remote=remote, url="https://123/c123", content_artifact=ca
    )


async def create_distribution(remote):
    name = str(uuid.uuid4())
    return await Distribution.objects.acreate(name=name, base_path=name, remote=remote)


@pytest.mark.asyncio
@pytest.mark.django_db
async def test_pull_through_remote_artifact_exists(request123, tmp_path):
    """Remote Artifact already exists, stream or serve associated content."""
    handler = Handler()
    handler._stream_content_artifact = AsyncMock()

    # Setup content w/ remote artifact
    content = await create_content()
    ca = await create_content_artifact(content)
    remote = await create_remote()
    await create_remote_artifact(remote, ca)
    distro = await create_distribution(remote)

    # Check that the handler finds the on-demand CA and calls the stream method
    try:
        await handler._match_and_stream(f"{distro.base_path}/c123", request123)
        handler._stream_content_artifact.assert_called_once()
        assert ca in handler._stream_content_artifact.call_args[0]

        # Manually save artifact for content_artifact
        tmp_file = tmp_path / str(uuid.uuid4())
        tmp_file.write_text(str(tmp_file))
        artifact = Artifact.init_and_validate(str(tmp_file))
        await artifact.asave()

        ca.artifact = artifact
        await ca.asave()
        handler._serve_content_artifact = AsyncMock()

        # Check that the handler finds the CA and calls the serve method
        await handler._match_and_stream(f"{distro.base_path}/c123", request123)
        handler._serve_content_artifact.assert_called_once()
        assert ca in handler._serve_content_artifact.call_args[0]
    finally:
        # Cleanup since this test isn't using fixtures
        await content.adelete()
        await remote.adelete()
        await distro.adelete()


@pytest.mark.asyncio
@pytest.mark.django_db
async def test_pull_through_new_remote_artifacts(request123, monkeypatch):
    """Remote Artifact doesn't exist, create and stream content."""
    handler = Handler()
    handler._stream_remote_artifact = AsyncMock()

    remote = await create_remote()
    monkeypatch.setattr(Remote, "get_remote_artifact_content_type", Mock(return_value=Content))
    distro = await create_distribution(remote)

    try:
        await handler._match_and_stream(f"{distro.base_path}/c123", request123)
        remote.get_remote_artifact_content_type.assert_called_once_with("c123")
        handler._stream_remote_artifact.assert_called_once()

        args, kwargs = handler._stream_remote_artifact.call_args
        assert kwargs.get("save_artifact", None) is True
        ra = args[2]
        assert isinstance(ra, RemoteArtifact)
        assert ra.remote == remote
        assert ra.url == f"{remote.url}/c123"
        assert ra.content_artifact.relative_path == "c123"
    finally:
        await remote.adelete()
        await distro.adelete()


@pytest.mark.asyncio
@pytest.mark.django_db
async def test_pull_through_metadata_file(request123, monkeypatch):
    """Requested path is for a metadata file. Don't save response."""
    handler = Handler()
    handler._stream_remote_artifact = AsyncMock()

    remote = await create_remote()
    monkeypatch.setattr(Remote, "get_remote_artifact_content_type", Mock(return_value=None))
    distro = await create_distribution(remote)

    try:
        await handler._match_and_stream(f"{distro.base_path}/c123", request123)
        remote.get_remote_artifact_content_type.assert_called_once_with("c123")
        handler._stream_remote_artifact.assert_called_once()

        _, kwargs = handler._stream_remote_artifact.call_args
        assert kwargs.get("save_artifact", None) is False
    finally:
        await remote.adelete()
        await distro.adelete()


def test_pull_through_save_single_artifact_content(
    remote123, request123, download_result_mock, monkeypatch
):
    """Ensure single-artifact content is properly saved on pull-through."""
    handler = Handler()
    remote123.get_remote_artifact_content_type = Mock(return_value=Content)
    content_init_mock = Mock(return_value=Content())
    monkeypatch.setattr(Content, "init_from_artifact_and_relative_path", content_init_mock)
    ca = ContentArtifact(relative_path="c123")
    ra = RemoteArtifact(url=f"{remote123.url}/c123", remote=remote123, content_artifact=ca)

    # Content is saved during handler._save_artifact
    artifact = handler._save_artifact(download_result_mock, ra, request=request123)

    remote123.get_remote_artifact_content_type.assert_called_once_with("c123")
    content_init_mock.assert_called_once_with(artifact, "c123")

    # Assert the CA and RA are properly saved
    ca = artifact.content_memberships.first()
    assert ca.content is not None
    assert ca.relative_path == "c123"
    ra = RemoteArtifact.objects.filter(
        url=f"{remote123.url}/c123", remote=remote123, content_artifact=ca
    ).first()
    assert ra is not None


def test_pull_through_save_multi_artifact_content(
    remote123, request123, download_result_mock, monkeypatch, tmp_path
):
    """Ensure multi-artifact content is properly saved on pull-through."""
    handler = Handler()
    remote123.get_remote_artifact_content_type = Mock(return_value=Content)

    tmp_file = tmp_path / str(uuid.uuid4())
    tmp_file.write_text(str(tmp_file))
    artifact123 = Artifact.init_and_validate(str(tmp_file))
    artifact123.save()

    def content_init(art, path):
        return Content(), {path: artifact123, path + "abc": art}

    monkeypatch.setattr(Content, "init_from_artifact_and_relative_path", content_init)
    ca = ContentArtifact(relative_path="c123")
    ra = RemoteArtifact(url=f"{remote123.url}/c123", remote=remote123, content_artifact=ca)

    artifact = handler._save_artifact(download_result_mock, ra, request123)

    ca = artifact.content_memberships.first()
    assert ca.content is not None

    artifacts = set(ca.content._artifacts.all())
    assert len(artifacts) == 2
    assert {artifact, artifact123} == artifacts


import select
from multiprocessing import Process, Queue

import requests


def run_server(port: int, server_dir: str, q: Queue):
    import http.server
    import os

    handler_cls = http.server.SimpleHTTPRequestHandler
    server_cls = http.server.HTTPServer

    os.chdir(server_dir)
    server_address = ("", port)
    httpd = server_cls(server_address, handler_cls)

    q.put(httpd.fileno())  # send to parent so can use select
    httpd.serve_forever()




def create_server(port: int, server_dir: str) -> Process:
    # setup/teardown server
    q = Queue()
    proc = Process(target=run_server, args=(port, server_dir, q))
    proc.start()

    # block until the server socket fd is ready for write
    server_socket_fd = q.get()
    _, w, _ = select.select([], [server_socket_fd], [], 5)
    if not w:
        proc.terminate()
        proc.join()
        raise TimeoutError("The test server didnt get ready.")
    return proc
    

@pytest.fixture
def server_a(tmp_path):
    # setup data
    server_dir = tmp_path / "server_a"
    server_dir.mkdir()
    blob_a = server_dir / "blob"
    blob_a.write_bytes(b"aaa")
    # setup server
    port = 8787
    proc = create_server(port, server_dir)
    base_url = f"http://localhost:{port}"
    yield base_url
    proc.terminate()
    proc.join()


@pytest.fixture
def server_b(tmp_path):
    # setup data
    server_dir = tmp_path / "server_b"
    server_dir.mkdir()
    blob_a = server_dir / "blob"
    blob_a.write_bytes(b"bbb")
    # setup server
    port = 8788
    proc = create_server(port, server_dir)
    base_url = f"http://localhost:{port}"
    yield base_url
    proc.terminate()
    proc.join()


def test_mock_server(server_a, server_b):
    response = requests.get(server_a + "/blob")
    assert response.status_code == 200
    assert b"aaa" == response.content

    response = requests.get(server_b + "/blob")
    assert response.status_code == 200
    assert b"bbb" == response.content



@pytest.mark.asyncio
@pytest.mark.django_db
async def test_server_client_setup(monkeypatch, server_a, server_b):
    async def delete_all_objects(model):
        await sync_to_async(model.objects.all().delete)()
    for m in (Remote, Distribution, ContentArtifact, Content, RemoteArtifact, Artifact):
        await delete_all_objects(m)
        
    expected_aaa_digest = hashlib.sha256(b"aaa").hexdigest()
    # broken remote server setup
    monkeypatch.setattr(Remote, "get_remote_artifact_content_type", Mock(return_value=Content))
    monkeypatch.setattr(Content, "init_from_artifact_and_relative_path", Mock(return_value=Content()))
    content = await Content.objects.acreate()
    ca = await ContentArtifact.objects.acreate(content=content)

    remote_a = await Remote.objects.acreate(name="server_a", url=server_a)
    ra_a = await RemoteArtifact.objects.acreate(content_artifact=ca, remote=remote_a, sha256=expected_aaa_digest)

    # pulp expects aaa for ra_b, but server_b updated and we didnt sync, so should fail
    remote_b = await Remote.objects.acreate(name="server_b", url=server_b)
    ra_b = await RemoteArtifact.objects.acreate(content_artifact=ca, remote=remote_b, sha256=expected_aaa_digest)

    dist = await Distribution.objects.acreate(name="mydist", base_path="mydist", remote=remote_b)

    resources = [remote_a, remote_b, content, ca, ra_b, ra_a, dist]

    # run aiohttp server and client
    app = await server()
    client = TestClient(TestServer(app))
    await client.start_server()

    # asserts
    async def assert_content_in(path, content):
        resp = await client.get(path)
        assert resp.status == 200
        text = await resp.text()
        assert content in text

    async def assert_can_get_blob():
        resp = await client.get("/pulp/content/mydist/blob")
        assert resp.status == 200
        text = await resp.text()
        assert "aaa" in text

    try:
        await assert_content_in("/pulp/content/", content="Index of /pulp/content/")
        await assert_content_in("/pulp/content/mydist/", content="blob")
        # TODO: the content handler is going through the pull-through caching and calling
        # _stream_remote_artifact(), but I need to make it call _stream_content_artifact(),
        # so I can test the RA selection/retry.
        await assert_can_get_blob()
    finally:
        await client.close()
        for item in resources:
            await item.adelete()

