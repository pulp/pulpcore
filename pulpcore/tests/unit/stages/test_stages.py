import asyncio
import pytest

import mock

from pulpcore.plugin.stages import Stage, EndStage, DeclarativeContent


pytestmark = pytest.mark.usefixtures("fake_domain")


@pytest.fixture
def in_q():
    return asyncio.Queue()


@pytest.fixture
def stage(in_q):
    stage = Stage()
    stage._connect(in_q, None)
    return stage


@pytest.mark.asyncio
async def test_single_batch_and_none(stage, in_q):
    c1 = mock.Mock()
    c2 = mock.Mock()
    in_q.put_nowait(c1)
    in_q.put_nowait(c2)
    in_q.put_nowait(None)
    batch_it = stage.batches(minsize=1)
    assert [c1, c2] == await batch_it.__anext__()
    with pytest.raises(StopAsyncIteration):
        await batch_it.__anext__()


@pytest.mark.asyncio
async def test_none_only(stage, in_q):
    in_q.put_nowait(None)
    batch_it = stage.batches(minsize=1)
    with pytest.raises(StopAsyncIteration):
        await batch_it.__anext__()


@pytest.mark.asyncio
async def test_batch_and_single_none(stage, in_q):
    c1 = mock.Mock()
    c2 = mock.Mock()
    in_q.put_nowait(c1)
    in_q.put_nowait(c2)
    batch_it = stage.batches(minsize=1)
    assert [c1, c2] == await batch_it.__anext__()
    in_q.put_nowait(None)
    with pytest.raises(StopAsyncIteration):
        await batch_it.__anext__()


@pytest.mark.asyncio
async def test_two_batches(stage, in_q):
    c1 = mock.Mock()
    c2 = mock.Mock()
    c3 = mock.Mock()
    c4 = mock.Mock()
    in_q.put_nowait(c1)
    in_q.put_nowait(c2)
    batch_it = stage.batches(minsize=1)
    assert [c1, c2] == await batch_it.__anext__()
    in_q.put_nowait(c3)
    in_q.put_nowait(c4)
    in_q.put_nowait(None)
    assert [c3, c4] == await batch_it.__anext__()
    with pytest.raises(StopAsyncIteration):
        await batch_it.__anext__()


@pytest.mark.asyncio
async def test_thaw_queue(stage, in_q):
    # Test that awaiting `resolved` on DeclarativeContent does not dead lock
    c1 = DeclarativeContent(mock.Mock())
    c2 = DeclarativeContent(mock.Mock())
    c3 = DeclarativeContent(mock.Mock())
    c4 = DeclarativeContent(mock.Mock())
    batch_it = stage.batches(minsize=4)
    fetch_task = asyncio.ensure_future(batch_it.__anext__())
    fetch_task.add_done_callback(lambda _: c2.resolve())
    in_q.put_nowait(c1)
    in_q.put_nowait(c2)
    in_q.put_nowait(c3)
    wait_task = asyncio.ensure_future(c2.resolution())
    wait_task.add_done_callback(lambda _: in_q.put_nowait(c4))
    batch, c2_res = await asyncio.gather(fetch_task, wait_task)
    assert [c1, c2, c3] == batch
    assert c2.content == c2_res
    in_q.put_nowait(None)
    assert [c4] == await batch_it.__anext__()
    with pytest.raises(StopAsyncIteration):
        await batch_it.__anext__()


class FirstStage(Stage):
    def __init__(self, num, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.num = num

    async def run(self):
        for i in range(self.num):
            await asyncio.sleep(0)  # Force reschedule
            await self.put(mock.Mock())


class MiddleStage(Stage):
    def __init__(self, num, minsize, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.num = num
        self.minsize = minsize

    async def run(self):
        async for batch in self.batches(self.minsize):
            assert batch
            assert len(batch) >= min(self.minsize, self.num)
            self.num -= len(batch)
            for b in batch:
                await self.put(b)
        assert self.num == 0


class LastStage(Stage):
    def __init__(self, num, minsize, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.num = num
        self.minsize = minsize

    async def run(self):
        async for batch in self.batches(self.minsize):
            assert batch
            assert len(batch) >= min(self.minsize, self.num)
            self.num -= len(batch)
        assert self.num == 0


@pytest.mark.asyncio
async def test_batch_queue_and_min_sizes():
    """Test batches iterator in a small stages setting with various sizes"""
    for num in range(10):
        for minsize in range(1, 5):
            for qsize in range(1, num + 1):
                queues = [asyncio.Queue(maxsize=qsize) for i in range(3)]
                first_stage = FirstStage(num)
                middle_stage = MiddleStage(num, minsize)
                last_stage = LastStage(num, minsize)
                end_stage = EndStage()
                first_stage._connect(None, queues[0])
                middle_stage._connect(queues[0], queues[1])
                last_stage._connect(queues[1], queues[2])
                end_stage._connect(queues[2], None)
                await asyncio.gather(last_stage(), middle_stage(), first_stage(), end_stage())
