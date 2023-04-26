import asyncio
import pytest
import pytest_asyncio
from uuid import uuid4
from contextlib import suppress
from aiotools.timer import VirtualClock

from unittest import mock

from pulpcore.plugin.stages import DeclarativeContent, DeclarativeArtifact
from pulpcore.plugin.stages.artifact_stages import ArtifactDownloader

pytestmark = pytest.mark.usefixtures("fake_domain")


class MockException(Exception):
    """
    A tracer exception.
    """

    pass


class DownloaderMock:
    """Mock for a Downloader.

    URLs are expected to be the delay to wait to simulate downloading,
    e.g `url='5'` will wait for 5 seconds. Negative numbers will raise
    an exception after waiting for the absolute value, e.g. `url=-5` fails
    after 5 seconds.
    """

    def __init__(self, **kwargs):
        self.running = 0
        self.downloads = 0
        self.canceled = 0

    def __call__(self, url, **kwargs):
        class _DownloaderMock:
            def __init__(this, url, **kwargs):
                this.url = url

            async def run(this, extra_data=None):
                self.running += 1
                try:
                    duration = int(this.url)
                    await asyncio.sleep(abs(duration))
                    if duration < 0:
                        raise MockException("Download Failed")
                except asyncio.CancelledError:
                    self.running -= 1
                    self.canceled += 1
                    raise
                self.running -= 1
                self.downloads += 1
                result = mock.Mock()
                result.url = this.url
                result.artifact_attributes = {}
                return result

        return _DownloaderMock(url, **kwargs)


@pytest_asyncio.fixture
async def advance():
    async def _advance(sec):
        await asyncio.sleep(sec)

    with VirtualClock().patch_loop():
        yield _advance


@pytest.fixture
def in_q():
    return asyncio.Queue()


@pytest.fixture
def out_q():
    return asyncio.Queue()


@pytest.fixture
def downloader_mock():
    return DownloaderMock()


@pytest.fixture
def queue_dc(in_q, downloader_mock):
    def _queue_dc(delays=[], artifact_path=None):
        """Put a DeclarativeContent instance into `in_q`

        For each `delay` in `delays`, associate a DeclarativeArtifact
        with download duration `delay` to the content unit. `delay ==
        None` means that the artifact is already present (pk is set)
        and no download is required. `artifact_path != None` means
        that the Artifact already has a file associated with it and a
        download does not need to be scheduled.
        """
        das = []
        for delay in delays:
            artifact = mock.Mock()
            artifact.pk = uuid4()
            artifact._state.adding = delay is not None
            artifact.DIGEST_FIELDS = []
            artifact.file = artifact_path
            remote = mock.Mock()
            remote.get_downloader = downloader_mock
            das.append(
                DeclarativeArtifact(
                    artifact=artifact, url=str(delay), relative_path="path", remote=remote
                )
            )
        dc = DeclarativeContent(content=mock.Mock(), d_artifacts=das)
        in_q.put_nowait(dc)

    return _queue_dc


@pytest_asyncio.fixture
async def download_task(event_loop, in_q, out_q):
    async def _download_task():
        """
        A coroutine running the downloader stage with a mocked ProgressReport.

        Returns:
            The done count of the ProgressReport.
        """
        with mock.patch("pulpcore.plugin.stages.artifact_stages.ProgressReport") as pb:
            pb.return_value.__aenter__.return_value.done = 0
            ad = ArtifactDownloader(max_concurrent_content=3)
            ad._connect(in_q, out_q)
            await ad()
        return pb.return_value.__aenter__.return_value.done

    task = event_loop.create_task(_download_task())
    yield task
    if not task.done():
        task.cancel()
    with suppress(asyncio.CancelledError, MockException):
        await task


@pytest.mark.asyncio
async def test_downloads(advance, downloader_mock, download_task, in_q, out_q, queue_dc):
    # Create 28 content units, every third one must be downloaded.
    # The downloads take 0, 3, 6,..., 27 seconds; content units
    # 1, 2, 4, 5, ..., 26 do not need downloads.
    for i in range(28):
        queue_dc(delays=[i if not i % 3 else None])
    in_q.put_nowait(None)

    # At 0.5 seconds
    await advance(0.5)
    # 3, 6 and 9 are running. 0 is finished
    assert downloader_mock.running == 3
    # non-downloads 1, 2, 4, 5, 7, 8 are forwarded
    assert out_q.qsize() == 7
    # 9 - 26, None are waiting to be picked up
    assert in_q.qsize() == 19

    # Two downloads run in parallel. The most asymmetric way
    # to schedule the remaining downloads is:
    # 3, 12, 21: finished after 36 seconds
    # 6, 15, 24: finished after 45 seconds
    # 9, 18, 27: finished after 54 seconds
    # until 35.5 seconds three downloads must run
    for t in range(35):
        await advance(1.0)
        assert downloader_mock.running == 3

    # At 54.5 seconds, the stage is done at the latest
    await advance(19.0)
    assert downloader_mock.running == 0
    assert downloader_mock.downloads == 10
    assert download_task.result() == downloader_mock.downloads
    assert in_q.qsize() == 0
    assert out_q.qsize() == 29
    assert download_task.result() == 10


@pytest.mark.asyncio
async def test_multi_artifact_downloads(
    advance, downloader_mock, download_task, in_q, out_q, queue_dc
):
    # Content units should fill the slot like
    #
    # 0   1   2   3 s
    # .   .   .   .
    # +---+-------+
    # | 1 |   4   |
    # +---+---+---+
    # |   2   |
    # +-------+
    # |   3   |
    # +-------+
    #

    queue_dc(delays=[])  # must be forwarded to next stage immediately
    queue_dc(delays=[1])
    queue_dc(delays=[2, 2])
    queue_dc(delays=[2])
    queue_dc(delays=[2, None])  # schedules only one download
    in_q.put_nowait(None)

    # At 0.5 seconds, three content units are downloading with four
    # downloads overall
    await advance(0.5)
    assert downloader_mock.running == 4
    assert out_q.qsize() == 1

    # At 1.5 seconds, the download for the first content unit has completed.
    # At 1 second, the download of the forth content unit is started
    await advance(1.0)
    assert downloader_mock.running == 4
    assert out_q.qsize() == 2

    # At 2.5 seconds, the downloads for the second and the third content unit
    # have completed
    await advance(1.0)
    assert downloader_mock.running == 1
    assert out_q.qsize() == 4

    # At 3.5 seconds, stage must de done
    await advance(1.0)
    assert downloader_mock.running == 0
    assert downloader_mock.downloads == 5
    assert in_q.qsize() == 0
    assert out_q.qsize() == 6

    assert download_task.result() == 5


@pytest.mark.asyncio
async def test_sparse_batches_dont_block_stage(
    advance, downloader_mock, download_task, in_q, out_q, queue_dc
):
    """Regression test for issue https://pulp.plan.io/issues/4018."""

    def queue_content_with_a_single_download(batchsize=100, delay=100):
        """
        Queue a batch of `batchsize` declarative_content instances. Only the
        first one triggers a download of duration `delay`.
        """
        queue_dc(delays=[delay])
        for i in range(batchsize - 1):
            queue_dc([None])

    queue_content_with_a_single_download()

    # At 0.5 seconds, the first content unit is downloading
    await advance(0.5)
    assert downloader_mock.running == 1
    assert out_q.qsize() == 99

    # at 0.5 seconds next batch arrives (last batch)
    queue_content_with_a_single_download()
    in_q.put_nowait(None)

    # at 1.0 seconds, two downloads are running
    await advance(0.5)
    assert downloader_mock.running == 2
    assert out_q.qsize() == 2 * 99

    # at 101 seconds, stage should have completed
    await advance(100)

    assert downloader_mock.running == 0
    assert downloader_mock.downloads == 2
    assert in_q.qsize() == 0
    assert out_q.qsize() == 201

    assert download_task.result() == 2


@pytest.mark.asyncio
async def test_cancel(advance, downloader_mock, download_task, in_q, out_q, queue_dc):
    for i in range(4):
        queue_dc(delays=[100])
    in_q.put_nowait(None)

    # After 0.5 seconds, the three downloads must have started
    await advance(0.5)
    assert downloader_mock.running == 3

    download_task.cancel()

    await advance(0.5)

    with pytest.raises(asyncio.CancelledError):
        download_task.result()
    assert downloader_mock.running == 0
    assert downloader_mock.canceled == 3


@pytest.mark.asyncio
async def test_exception_with_empty_in_q(
    advance, downloader_mock, download_task, in_q, out_q, queue_dc
):
    # Create three content units with 1 downloads, followed by one thowing an exception.
    queue_dc(delays=[1])
    queue_dc(delays=[2])
    queue_dc(delays=[2])
    queue_dc(delays=[-1])

    # At 0.5 seconds
    await advance(0.5)
    # 3 downloads are running. No unit is finished
    assert downloader_mock.running == 3
    assert in_q.qsize() == 1
    assert out_q.qsize() == 0

    # At 1.5 seconds
    await advance(1.0)
    # 3 downloads are running. One unit is finished.
    assert downloader_mock.running == 3
    assert in_q.qsize() == 0
    assert out_q.qsize() == 1

    # At 2.5 seconds, the exception must have been triggered
    await advance(1.0)
    assert download_task.done()
    assert isinstance(download_task.exception(), MockException)


@pytest.mark.asyncio
async def test_exception_finished_in_q(
    advance, downloader_mock, download_task, in_q, out_q, queue_dc
):
    # Create three content units with 1 downloads, followed by one thowing an exception.
    queue_dc(delays=[1])
    queue_dc(delays=[2])
    queue_dc(delays=[2])
    queue_dc(delays=[-1])
    await in_q.put(None)

    # At 0.5 seconds
    await advance(0.5)
    # 3 downloads are running. No unit is finished
    assert downloader_mock.running == 3
    assert in_q.qsize() == 2
    assert out_q.qsize() == 0

    # At 1.5 seconds
    await advance(1.0)
    # 3 downloads are running. One unit is finished.
    assert downloader_mock.running == 3
    assert in_q.qsize() == 1
    assert out_q.qsize() == 1

    # At 2.5 seconds, the exception must have been triggered
    await advance(1.0)
    assert download_task.done()
    assert isinstance(download_task.exception(), MockException)


@pytest.mark.asyncio
async def test_exception_with_saturated_content_slots(
    advance, downloader_mock, download_task, in_q, out_q, queue_dc
):
    # Create three content units with 1 downloads, followed by one thowing an exception.
    queue_dc(delays=[1])
    queue_dc(delays=[3])
    queue_dc(delays=[3])
    queue_dc(delays=[-1])
    queue_dc(delays=[1])  # This unit will be waiting for a free slot

    # At 0.5 seconds
    await advance(0.5)
    # 3 downloads are running. No unit is finished
    assert downloader_mock.running == 3
    assert in_q.qsize() == 2
    assert out_q.qsize() == 0

    # At 1.5 seconds
    await advance(1.0)
    # 3 downloads are running. One unit is finished.
    assert downloader_mock.running == 3
    assert in_q.qsize() == 1
    assert out_q.qsize() == 1

    # At 2.5 seconds, the exception must have been triggered
    await advance(1.0)
    assert download_task.done()
    assert isinstance(download_task.exception(), MockException)

    # At 3.5 seconds, the task should be done
    await advance(1.0)
    assert download_task.done()
    assert isinstance(download_task.exception(), MockException)


@pytest.mark.asyncio
async def test_download_artifact_with_file(
    advance, downloader_mock, download_task, in_q, out_q, queue_dc
):
    # Create 3 downloads with Artifacts that already have a file
    queue_dc(delays=[1, 2, 3], artifact_path="/foo/bar")
    # Create 3 downloads with Artifacts that don't have a file
    queue_dc(delays=[1, 2, 3], artifact_path=None)
    in_q.put_nowait(None)

    # At 0.5 seconds only 3 should be running and 0 done
    await advance(0.5)
    assert downloader_mock.downloads == 0
    assert downloader_mock.running == 3

    # At 3.5 seconds all 3 should be done
    await advance(3.0)
    assert downloader_mock.downloads == 3
    assert downloader_mock.running == 0

    assert download_task.result() == 3
