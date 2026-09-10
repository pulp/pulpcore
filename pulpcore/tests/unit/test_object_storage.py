import asyncio
from unittest.mock import AsyncMock, Mock

import pytest

from pulpcore._object_storage import AzureStream, S3Stream, get_stream


class S3Body:
    def __init__(self):
        self.read_sizes = []
        self.closed = False

    def read(self, size):
        self.read_sizes.append(size)
        return b"abc"[:size]

    def close(self):
        self.closed = True


def test_s3_stream_normalizes_name_and_filters_download_parameters():
    """Preserve S3 locations and read-specific options when bypassing `Storage.open()`.

    The temporary adapter calls the provider directly, so this protects against
    losing a configured location prefix or security-related object parameters.
    """
    body = S3Body()
    client = Mock()
    client.get_object.return_value = {"Body": body}
    storage = Mock()
    storage.location = "prefix"
    storage.bucket_name = "bucket"
    storage.connection.meta.client = client
    storage._normalize_name.side_effect = lambda name: f"prefix/{name}"
    storage.get_object_parameters.return_value = {
        "SSECustomerAlgorithm": "AES256",
        "RequestPayer": "requester",
        "VersionId": "version",
        "ChecksumMode": "ENABLED",
        "ExpectedBucketOwner": "owner",
        "ContentType": "not-a-download-argument",
    }

    stream = S3Stream(storage, "./artifact/name", 3, 10)
    assert stream.open() is stream
    storage._normalize_name.assert_called_once_with("artifact/name")
    storage.get_object_parameters.assert_called_once_with("artifact/name")
    assert client.get_object.call_args.kwargs == {
        "SSECustomerAlgorithm": "AES256",
        "RequestPayer": "requester",
        "VersionId": "version",
        "ChecksumMode": "ENABLED",
        "ExpectedBucketOwner": "owner",
        "Bucket": "bucket",
        "Key": "prefix/artifact/name",
        "Range": "bytes=3-12",
    }

    assert stream.read(2) == b"ab"
    stream.close()
    assert body.read_sizes == [2]
    assert body.closed


def test_azure_stream_uses_ranged_chunks_and_bounds_reads():
    """Adapt Azure's provider-sized chunks to bounded reads without changing its range."""
    downloader = Mock()
    downloader.chunks.return_value = iter((b"ab", b"cdef", b"gh"))
    client = Mock()
    client.download_blob.return_value = downloader
    storage = Mock()
    storage.timeout = 17
    storage.client = client
    storage._get_valid_path.side_effect = lambda name: f"prefix/{name}"

    stream = AzureStream(storage, "artifact/name", 3, 8)
    assert stream.open() is stream
    assert client.download_blob.call_args.kwargs == {
        "offset": 3,
        "length": 8,
        "timeout": 17,
    }
    assert client.download_blob.call_args.args == ("prefix/artifact/name",)
    assert stream.read(3) == b"abc"
    assert stream.read(3) == b"def"
    assert stream.read(10) == b"gh"

    stream.close()
    downloader.close.assert_called_once_with()


def test_unknown_storage_class_keeps_file_object_fallback():
    """Keep unsupported backends on the established generic storage code path."""
    assert get_stream("pulpcore.app.models.storage.FileSystem", Mock(), "name", 0, 1) is None


def test_response_closes_object_stream_after_write_failure(monkeypatch):
    """Release the provider response when the client disconnects during a write."""
    asyncio.run(_test_response_closes_object_stream_after_write_failure(monkeypatch))


async def _test_response_closes_object_stream_after_write_failure(monkeypatch):
    from aiohttp.web import StreamResponse

    from pulpcore.responses import ArtifactResponse

    writer = Mock()
    writer.write = AsyncMock(side_effect=RuntimeError("client disconnected"))
    stream = Mock()
    stream.open.return_value = stream
    stream.read.return_value = b"abc"

    async def prepare(_self, _request):
        return writer

    monkeypatch.setattr(StreamResponse, "prepare", prepare)
    response = ArtifactResponse(artifact=Mock(), chunk_size=4)

    with pytest.raises(RuntimeError, match="client disconnected"):
        await response._sendfile_object_storage(Mock(), stream, 3)

    stream.close.assert_called_once_with()


def test_response_closes_object_stream_after_open_failure(monkeypatch):
    """Attempt adapter cleanup even when opening the provider stream raises."""
    asyncio.run(_test_response_closes_object_stream_after_open_failure(monkeypatch))


async def _test_response_closes_object_stream_after_open_failure(monkeypatch):
    from aiohttp.web import StreamResponse

    from pulpcore.responses import ArtifactResponse

    writer = Mock()
    stream = Mock()
    stream.open.side_effect = RuntimeError("provider unavailable")

    async def prepare(_self, _request):
        return writer

    monkeypatch.setattr(StreamResponse, "prepare", prepare)
    response = ArtifactResponse(artifact=Mock(), chunk_size=4)

    with pytest.raises(RuntimeError, match="provider unavailable"):
        await response._sendfile_object_storage(Mock(), stream, 3)

    stream.close.assert_called_once_with()


def test_artifact_response_dispatches_s3_stream_without_file_reads(monkeypatch):
    """Use the adapter for S3 so django-storages cannot eagerly spool the object."""
    asyncio.run(_test_artifact_response_dispatches_s3_stream_without_file_reads(monkeypatch))


async def _test_artifact_response_dispatches_s3_stream_without_file_reads(monkeypatch):
    from pulpcore.responses import ArtifactResponse

    storage = Mock()
    domain = Mock(storage_class="storages.backends.s3.S3Storage")
    domain.get_storage.return_value = storage
    artifact = Mock(pulp_domain=domain)
    file_object = Mock()
    file_object.name = "artifact/name"
    object_stream = Mock()
    response = ArtifactResponse(artifact=artifact)
    response._sendfile_object_storage = AsyncMock(return_value="writer")

    def get_stream(storage_class, selected_storage, name, offset, count):
        assert storage_class == "storages.backends.s3.S3Storage"
        assert selected_storage is storage
        assert name == "artifact/name"
        assert offset == 11
        assert count == 19
        return object_stream

    monkeypatch.setattr("pulpcore.responses.get_stream", get_stream)

    assert await response._sendfile("request", file_object, 11, 19) == "writer"
    domain.get_storage.assert_called_once_with()
    response._sendfile_object_storage.assert_awaited_once_with("request", object_stream, 19)
    file_object.seek.assert_not_called()
    file_object.read.assert_not_called()


def test_artifact_response_keeps_file_fallback_for_unsupported_storage(monkeypatch):
    """Retain the previous seek-and-read behavior for non-adapter storage backends."""
    asyncio.run(_test_artifact_response_keeps_file_fallback_for_unsupported_storage(monkeypatch))


async def _test_artifact_response_keeps_file_fallback_for_unsupported_storage(monkeypatch):
    from aiohttp.web import StreamResponse

    from pulpcore.responses import ArtifactResponse

    writer = Mock()
    writer.write = AsyncMock()
    writer.drain = AsyncMock()

    async def prepare(_self, _request):
        return writer

    monkeypatch.setattr(StreamResponse, "prepare", prepare)
    monkeypatch.setattr(
        "pulpcore.responses.get_stream", Mock(side_effect=AssertionError("adapter selected"))
    )

    domain = Mock(storage_class="pulpcore.app.models.storage.FileSystem")
    artifact = Mock(pulp_domain=domain)
    file_object = Mock()
    file_object.name = "artifact/name"
    file_object.read.return_value = b"payload"
    response = ArtifactResponse(artifact=artifact, chunk_size=8)

    assert await response._sendfile("request", file_object, 3, 7) is writer
    domain.get_storage.assert_not_called()
    file_object.seek.assert_called_once_with(3)
    file_object.read.assert_called_once_with(7)
    writer.write.assert_awaited_once_with(b"payload")
