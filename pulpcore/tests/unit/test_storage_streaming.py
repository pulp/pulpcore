"""Tests for bounded artifact streaming through Pulp's storage interface."""

import asyncio
import io
import threading
from contextlib import contextmanager
from unittest.mock import AsyncMock, Mock, call

import pytest


def _patch_response_prepare(monkeypatch, writer):
    from aiohttp.web import StreamResponse

    async def prepare(_self, _request):
        return writer

    monkeypatch.setattr(StreamResponse, "prepare", prepare)


def test_artifact_response_streams_requested_storage_range(monkeypatch):
    """Use the backend's ranged stream and send only the selected bytes."""
    asyncio.run(_test_artifact_response_streams_requested_storage_range(monkeypatch))


async def _test_artifact_response_streams_requested_storage_range(monkeypatch):
    from pulpcore.responses import ArtifactResponse

    writer = Mock()
    writer.write = AsyncMock()
    writer.drain = AsyncMock()
    _patch_response_prepare(monkeypatch, writer)

    stream = Mock()
    stream.read.side_effect = (b"bcd", b"")
    events = []

    @contextmanager
    def backend_stream(name, start=0, length=None):
        events.append(("open", name, start, length))
        try:
            yield stream
        finally:
            events.append(("close",))

    storage = Mock(open_stream=backend_stream)
    response = ArtifactResponse(artifact=Mock(), chunk_size=3)

    assert await response._sendfile("request", storage, "artifact/name", 1, 3) is writer
    assert writer.write.await_args_list == [call(b"bcd")]
    assert stream.read.call_args_list == [call(3)]
    assert events == [("open", "artifact/name", 1, 3), ("close",)]
    writer.drain.assert_awaited_once_with()


def test_artifact_response_bounds_reads_if_backend_returns_too_much(monkeypatch):
    """Do not write past the response length if a backend over-returns bytes."""
    asyncio.run(_test_artifact_response_bounds_reads_if_backend_returns_too_much(monkeypatch))


async def _test_artifact_response_bounds_reads_if_backend_returns_too_much(monkeypatch):
    from pulpcore.responses import ArtifactResponse

    writer = Mock()
    writer.write = AsyncMock()
    writer.drain = AsyncMock()
    _patch_response_prepare(monkeypatch, writer)

    stream = Mock()
    stream.read.return_value = b"beyond-range"
    storage = Mock(open_stream=Mock(return_value=_stream_context(stream)))
    response = ArtifactResponse(artifact=Mock(), chunk_size=16)

    assert await response._sendfile("request", storage, "artifact/name", 0, 3) is writer
    writer.write.assert_awaited_once_with(b"bey")
    stream.read.assert_called_once_with(3)


def test_artifact_response_closes_storage_stream_after_write_error(monkeypatch):
    """Pass write failures through the stream context so it can release resources."""
    asyncio.run(_test_artifact_response_closes_storage_stream_after_write_error(monkeypatch))


async def _test_artifact_response_closes_storage_stream_after_write_error(monkeypatch):
    from pulpcore.responses import ArtifactResponse

    writer = Mock()
    writer.write = AsyncMock(side_effect=RuntimeError("client disconnected"))
    writer.drain = AsyncMock()
    _patch_response_prepare(monkeypatch, writer)

    stream = Mock()
    stream.read.return_value = b"abc"
    observed_exceptions = []
    closed = []

    @contextmanager
    def backend_stream(*_args, **_kwargs):
        try:
            yield stream
        except BaseException as exc:
            observed_exceptions.append(exc)
            raise
        finally:
            closed.append(True)

    response = ArtifactResponse(artifact=Mock(), chunk_size=3)
    with pytest.raises(RuntimeError, match="client disconnected"):
        await response._sendfile("request", Mock(open_stream=backend_stream), "name", 0, 3)

    assert len(observed_exceptions) == 1
    assert str(observed_exceptions[0]) == "client disconnected"
    assert closed == [True]


def test_artifact_response_uses_storage_open_fallback(monkeypatch):
    """Keep the seekable-file fallback for storage backends without native streams."""
    asyncio.run(_test_artifact_response_uses_storage_open_fallback(monkeypatch))


async def _test_artifact_response_uses_storage_open_fallback(monkeypatch):
    from pulpcore.responses import ArtifactResponse

    writer = Mock()
    writer.write = AsyncMock()
    writer.drain = AsyncMock()
    _patch_response_prepare(monkeypatch, writer)

    file = io.BytesIO(b"abcdef")
    storage = Mock(spec=["open"])
    storage.open.return_value = file
    response = ArtifactResponse(artifact=Mock(), chunk_size=2)

    assert await response._sendfile("request", storage, "artifact/name", 2, 3) is writer
    assert writer.write.await_args_list == [call(b"cd"), call(b"e")]
    storage.open.assert_called_once_with("artifact/name", "rb")
    assert file.closed


def test_artifact_response_storage_io_runs_off_event_loop(monkeypatch):
    """Keep synchronous storage operations off the aiohttp event-loop thread."""
    asyncio.run(_test_artifact_response_storage_io_runs_off_event_loop(monkeypatch))


async def _test_artifact_response_storage_io_runs_off_event_loop(monkeypatch):
    from pulpcore.responses import ArtifactResponse

    event_loop_thread = threading.get_ident()
    io_threads = []

    class Stream:
        def read(self, _size):
            io_threads.append(threading.get_ident())
            return b"data"

    stream = Stream()

    @contextmanager
    def backend_stream(*_args, **_kwargs):
        io_threads.append(threading.get_ident())
        yield stream

    writer = Mock()
    writer.write = AsyncMock()
    writer.drain = AsyncMock()
    _patch_response_prepare(monkeypatch, writer)
    response = ArtifactResponse(artifact=Mock(), chunk_size=4)

    await response._sendfile("request", Mock(open_stream=backend_stream), "name", 0, 4)

    assert io_threads
    assert all(thread_id != event_loop_thread for thread_id in io_threads)


def _stream_context(stream):
    @contextmanager
    def context(*_args, **_kwargs):
        yield stream

    return context()
