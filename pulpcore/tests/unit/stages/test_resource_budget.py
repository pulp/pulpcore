import asyncio

import pytest

from pulpcore.plugin.stages import ArtifactResourceBudget


class TestAcquireRelease:
    """Basic acquire/release semantics."""

    @pytest.mark.asyncio
    async def test_acquire_and_release_items(self):
        budget = ArtifactResourceBudget(max_items=3)
        await budget.acquire(0)
        await budget.acquire(0)
        await budget.acquire(0)
        assert budget._current_items == 3
        budget.release(0)
        budget.release(0)
        budget.release(0)
        assert budget._current_items == 0

    @pytest.mark.asyncio
    async def test_acquire_and_release_bytes(self):
        budget = ArtifactResourceBudget(max_bytes=1000)
        await budget.acquire(400)
        await budget.acquire(400)
        assert budget._current_bytes == 800
        budget.release(400)
        assert budget._current_bytes == 400
        budget.release(400)
        assert budget._current_bytes == 0

    @pytest.mark.asyncio
    async def test_release_does_not_go_negative(self):
        budget = ArtifactResourceBudget(max_bytes=100, max_items=2)
        budget.release(500)
        assert budget._current_bytes == 0
        assert budget._current_items == 0


class TestBlocking:
    """Acquire blocks when budget is exhausted."""

    @pytest.mark.asyncio
    async def test_blocks_on_item_limit(self):
        budget = ArtifactResourceBudget(max_items=1)
        await budget.acquire(0)

        acquired = asyncio.Event()

        async def delayed_acquire():
            await budget.acquire(0)
            acquired.set()

        task = asyncio.ensure_future(delayed_acquire())
        await asyncio.sleep(0.05)
        assert not acquired.is_set(), "acquire should block when at item limit"

        budget.release(0)
        await asyncio.sleep(0.05)
        assert acquired.is_set(), "acquire should unblock after release"
        task.cancel()

    @pytest.mark.asyncio
    async def test_blocks_on_byte_limit(self):
        budget = ArtifactResourceBudget(max_bytes=100)
        await budget.acquire(80)

        acquired = asyncio.Event()

        async def delayed_acquire():
            await budget.acquire(50)
            acquired.set()

        task = asyncio.ensure_future(delayed_acquire())
        await asyncio.sleep(0.05)
        assert not acquired.is_set(), "acquire should block when bytes would exceed limit"

        budget.release(80)
        await asyncio.sleep(0.05)
        assert acquired.is_set(), "acquire should unblock after release"
        task.cancel()

    @pytest.mark.asyncio
    async def test_blocks_on_both_limits(self):
        """When both limits are set, both must be satisfied."""
        budget = ArtifactResourceBudget(max_bytes=1000, max_items=1)
        await budget.acquire(100)

        acquired = asyncio.Event()

        async def delayed_acquire():
            await budget.acquire(100)
            acquired.set()

        task = asyncio.ensure_future(delayed_acquire())
        await asyncio.sleep(0.05)
        assert not acquired.is_set()

        budget.release(100)
        await asyncio.sleep(0.05)
        assert acquired.is_set()
        task.cancel()


class TestDeadlockPrevention:
    """The _current_items == 0 guard prevents deadlock."""

    @pytest.mark.asyncio
    async def test_allows_oversized_item_when_empty(self):
        """A single item exceeding max_bytes is allowed when nothing is in flight."""
        budget = ArtifactResourceBudget(max_bytes=100)
        await budget.acquire(500)  # Should not block
        assert budget._current_bytes == 500
        assert budget._current_items == 1

    @pytest.mark.asyncio
    async def test_allows_item_over_item_limit_when_empty(self):
        """Even max_items=0 (if someone set it) doesn't block when nothing is in flight."""
        budget = ArtifactResourceBudget(max_items=0)
        # This would deadlock without the guard -- it should return immediately
        await budget.acquire(0)
        assert budget._current_items == 1

    @pytest.mark.asyncio
    async def test_second_oversized_item_blocks(self):
        """After allowing one oversized item through, the next must wait."""
        budget = ArtifactResourceBudget(max_bytes=100)
        await budget.acquire(500)

        acquired = asyncio.Event()

        async def delayed_acquire():
            await budget.acquire(50)
            acquired.set()

        task = asyncio.ensure_future(delayed_acquire())
        await asyncio.sleep(0.05)
        assert not acquired.is_set(), "second item should block while oversized item is in flight"

        budget.release(500)
        await asyncio.sleep(0.05)
        assert acquired.is_set()
        task.cancel()


class TestPressureEvent:
    """The pressure event signals downstream stages to flush."""

    @pytest.mark.asyncio
    async def test_pressure_set_when_blocked(self):
        budget = ArtifactResourceBudget(max_items=1)
        assert not budget.pressure.is_set()
        await budget.acquire(0)

        async def try_acquire():
            await budget.acquire(0)

        task = asyncio.ensure_future(try_acquire())
        await asyncio.sleep(0.05)
        assert budget.pressure.is_set(), "pressure should be set when acquire blocks"

        budget.release(0)
        await asyncio.sleep(0.05)
        assert not budget.pressure.is_set(), "pressure should clear after release"
        task.cancel()

    @pytest.mark.asyncio
    async def test_pressure_not_set_when_budget_available(self):
        budget = ArtifactResourceBudget(max_items=5)
        await budget.acquire(0)
        assert not budget.pressure.is_set()
        await budget.acquire(0)
        assert not budget.pressure.is_set()


class TestNoLimits:
    """When max_bytes and max_items are both None, acquire never blocks."""

    @pytest.mark.asyncio
    async def test_unlimited_acquires(self):
        budget = ArtifactResourceBudget(max_bytes=None, max_items=None)
        for i in range(100):
            await budget.acquire(1_000_000)
        assert budget._current_items == 100
        assert budget._current_bytes == 100_000_000


class TestConcurrentAcquireRelease:
    """Multiple concurrent acquires and releases behave correctly."""

    @pytest.mark.asyncio
    async def test_concurrent_producers_and_consumer(self):
        """Simulate multiple downloaders acquiring and a saver releasing."""
        budget = ArtifactResourceBudget(max_bytes=500, max_items=5)
        completed = []

        async def producer(item_id, size):
            await budget.acquire(size)
            await asyncio.sleep(0.01)  # simulate download
            completed.append(item_id)
            return size

        async def consumer():
            """Release budget periodically, simulating ArtifactSaver."""
            while len(completed) < 10:
                await asyncio.sleep(0.02)
                if budget._current_items > 0:
                    budget.release(100)

        consumer_task = asyncio.ensure_future(consumer())
        producer_tasks = [asyncio.ensure_future(producer(i, 100)) for i in range(10)]

        await asyncio.gather(*producer_tasks, consumer_task)
        assert len(completed) == 10
