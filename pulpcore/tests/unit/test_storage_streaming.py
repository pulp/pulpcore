"""Tests for ArtifactResponse's opt-in django-storages streaming path."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, Mock, call

import pytest


@pytest.mark.parametrize(
    "storage_class",
    (
        "storages.backends.s3.S3Storage",
        "storages.backends.s3boto3.S3Boto3Storage",
        "storages.backends.azure_storage.AzureStorage",
        "storages.backends.gcloud.GoogleCloudStorage",
    ),
)
def test_artifact_response_uses_open_stream_for_a_domain_storage(storage_class, monkeypatch):
    """Use the explicit storage API instead of opening a seekable temporary file."""

    asyncio.run(
        _test_artifact_response_uses_open_stream_for_a_domain_storage(storage_class, monkeypatch)
    )


async def _test_artifact_response_uses_open_stream_for_a_domain_storage(storage_class, monkeypatch):
    from aiohttp.web import StreamResponse

    from pulpcore.responses import ArtifactResponse

    writer = Mock()
    writer.write = AsyncMock()
    writer.drain = AsyncMock()
    stream = Mock()
    stream.read.side_effect = (b"abc", b"def", b"")
    stream_context = MagicMock()
    stream_context.__enter__.return_value = stream
    stream_opener = Mock(return_value=stream_context)
    storage = Mock(open_stream=stream_opener)
    domain = Mock(storage_class=storage_class)
    domain.get_storage.return_value = storage
    artifact = Mock(pulp_domain=domain)
    file_object = Mock()
    file_object.name = "artifact/name"

    async def prepare(_self, _request):
        return writer

    monkeypatch.setattr(StreamResponse, "prepare", prepare)
    response = ArtifactResponse(artifact=artifact, chunk_size=3)

    assert await response._sendfile("request", file_object, 11, 6) is writer
    stream_opener.assert_called_once_with("artifact/name", start=11, length=6)
    stream.read.assert_has_calls([call(3), call(3)])
    writer.write.assert_has_awaits([call(b"abc"), call(b"def")])
    stream_context.__exit__.assert_called_once_with(None, None, None)
    file_object.seek.assert_not_called()
    file_object.read.assert_not_called()


def test_artifact_response_limits_storage_stream_to_http_range(monkeypatch):
    """Never send bytes beyond the headers' selected HTTP range."""

    asyncio.run(_test_artifact_response_limits_storage_stream_to_http_range(monkeypatch))


async def _test_artifact_response_limits_storage_stream_to_http_range(monkeypatch):
    from aiohttp.web import StreamResponse

    from pulpcore.responses import ArtifactResponse

    writer = Mock()
    writer.write = AsyncMock()
    writer.drain = AsyncMock()
    stream = Mock()
    stream.read.return_value = b"provider returned too much"
    stream_context = MagicMock()
    stream_context.__enter__.return_value = stream

    async def prepare(_self, _request):
        return writer

    monkeypatch.setattr(StreamResponse, "prepare", prepare)
    response = ArtifactResponse(artifact=Mock(), chunk_size=10)

    assert (
        await response._sendfile_storage_stream(
            "request", Mock(return_value=stream_context), "artifact/name", 0, 3
        )
        is writer
    )
    writer.write.assert_awaited_once_with(b"pro")
    stream_context.__exit__.assert_called_once_with(None, None, None)


def test_artifact_response_closes_stream_context_after_write_error(monkeypatch):
    """Give the storage context the exception needed to release provider resources."""

    asyncio.run(_test_artifact_response_closes_stream_context_after_write_error(monkeypatch))


async def _test_artifact_response_closes_stream_context_after_write_error(monkeypatch):
    from aiohttp.web import StreamResponse

    from pulpcore.responses import ArtifactResponse

    writer = Mock()
    writer.write = AsyncMock(side_effect=RuntimeError("client disconnected"))
    stream = Mock()
    stream.read.return_value = b"abc"
    stream_context = MagicMock()
    stream_context.__enter__.return_value = stream

    async def prepare(_self, _request):
        return writer

    monkeypatch.setattr(StreamResponse, "prepare", prepare)
    response = ArtifactResponse(artifact=Mock(), chunk_size=3)

    with pytest.raises(RuntimeError, match="client disconnected"):
        await response._sendfile_storage_stream(
            "request", Mock(return_value=stream_context), "artifact/name", 0, 3
        )

    assert stream_context.__exit__.call_args.args[0] is RuntimeError
    assert str(stream_context.__exit__.call_args.args[1]) == "client disconnected"


def test_artifact_response_keeps_file_fallback_without_open_stream(monkeypatch):
    """Retain existing storage-file serving for filesystems and unsupported backends."""

    asyncio.run(_test_artifact_response_keeps_file_fallback_without_open_stream(monkeypatch))


async def _test_artifact_response_keeps_file_fallback_without_open_stream(monkeypatch):
    from aiohttp.web import StreamResponse

    from pulpcore.responses import ArtifactResponse

    writer = Mock()
    writer.write = AsyncMock()
    writer.drain = AsyncMock()
    storage = Mock(spec=[])
    domain = Mock(storage_class="pulpcore.app.models.storage.FileSystem")
    domain.get_storage.return_value = storage
    artifact = Mock(pulp_domain=domain)
    file_object = Mock()
    file_object.read.return_value = b"payload"

    async def prepare(_self, _request):
        return writer

    monkeypatch.setattr(StreamResponse, "prepare", prepare)
    response = ArtifactResponse(artifact=artifact, chunk_size=8)

    assert await response._sendfile("request", file_object, 3, 7) is writer
    file_object.seek.assert_called_once_with(3)
    file_object.read.assert_called_once_with(7)
    writer.write.assert_awaited_once_with(b"payload")
