"""Tests for RedisWorker.fetch_task() blocked-resource skip optimization.

These tests verify that when fetch_task() discovers a resource is blocked
(via acquire_locks failure), subsequent batch queries exclude tasks needing
that resource at the DB level.
"""

import os
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "pulpcore.app.settings")


def _make_task(pk=None, resources=None, domain_name="default"):
    """Create a mock Task with the given resources."""
    task = MagicMock()
    task.pk = pk or uuid4()
    task.reserved_resources_record = resources or []
    task.pulp_domain = MagicMock()
    task.pulp_domain.name = domain_name
    task._all_locks_released = False
    return task


def _make_worker():
    """Create a minimal RedisWorker-like object for testing fetch_task()."""
    from pulpcore.tasking.redis_worker import RedisWorker

    worker = object.__new__(RedisWorker)
    worker.ignored_task_ids = []
    worker.redis_conn = MagicMock()
    worker.name = "1@test-worker"
    worker.app_status = MagicMock()
    return worker


class ChainedQuerySet:
    """A mock QuerySet that tracks filter/exclude calls and returns
    pre-configured batches via slicing."""

    def __init__(self, batches):
        self.batches = list(batches)
        self.batch_index = 0
        self.calls = []

    def filter(self, **kwargs):
        self.calls.append(("filter", kwargs))
        return self

    def exclude(self, **kwargs):
        self.calls.append(("exclude", kwargs))
        return self

    def order_by(self, *args):
        return self

    def select_related(self, *args):
        return self

    def __getitem__(self, key):
        if self.batch_index < len(self.batches):
            batch = self.batches[self.batch_index]
            self.batch_index += 1
            return batch
        return []

    def get_overlap_excludes(self):
        return [
            c[1]["reserved_resources_record__overlap"]
            for c in self.calls
            if c[0] == "exclude" and "reserved_resources_record__overlap" in c[1]
        ]


@pytest.fixture
def patched_modules():
    """Patch the module-level imports used by fetch_task."""
    with (
        patch("pulpcore.tasking.redis_worker.extract_task_resources") as mock_extract,
        patch("pulpcore.tasking.redis_worker.get_task_lock_key") as mock_get_key,
        patch("pulpcore.tasking.redis_worker.acquire_locks") as mock_acquire,
        patch("pulpcore.tasking.redis_worker.safe_release_task_locks") as mock_release,
        patch("pulpcore.tasking.redis_worker.Task") as MockTask,
    ):
        mock_get_key.side_effect = lambda pk: f"task:{pk}"
        yield {
            "extract": mock_extract,
            "get_key": mock_get_key,
            "acquire": mock_acquire,
            "release": mock_release,
            "Task": MockTask,
        }


class TestFetchTaskBlockedResourceSkip:
    """Test that fetch_task skips tasks needing blocked resources."""

    def test_skips_blocked_resource_in_next_batch(self, patched_modules):
        """After discovering resource_a is blocked in batch 1, batch 2's
        DB query should exclude tasks needing resource_a and shared:resource_a."""
        resource_a = "prn:rpm.repository:aaa"
        resource_b = "prn:rpm.repository:bbb"

        task1 = _make_task(resources=[resource_a, "shared:prn:core.domain:ddd"])
        task2 = _make_task(resources=[resource_b, "shared:prn:core.domain:ddd"])

        patched_modules["extract"].side_effect = [
            ([resource_a], ["prn:core.domain:ddd"]),
            ([resource_b], ["prn:core.domain:ddd"]),
        ]
        patched_modules["acquire"].side_effect = [
            [resource_a],  # task1 blocked
            [],  # task2 locks acquired
        ]

        # Batch 1: task1 blocked → blocked_resources grows → loop re-queries.
        # Batch 2: task2 claimable.
        qs = ChainedQuerySet([[task1], [task2]])

        claim_qs = MagicMock()
        claim_qs.update.return_value = 1

        def filter_side_effect(**kwargs):
            if "pk" in kwargs:
                return claim_qs
            return qs

        patched_modules["Task"].objects.filter = filter_side_effect

        worker = _make_worker()
        result = worker.fetch_task()

        assert result is not None
        assert result.pk == task2.pk

        overlap_excludes = qs.get_overlap_excludes()
        assert len(overlap_excludes) >= 1
        assert resource_a in overlap_excludes[0]

    def test_does_not_add_task_lock_sentinel(self, patched_modules):
        """__task_lock__ from acquire_locks should not be added to
        the blocked_resources exclusion set."""
        resource_a = "prn:rpm.repository:aaa"
        task1 = _make_task(resources=[resource_a])

        patched_modules["extract"].return_value = ([resource_a], [])
        patched_modules["acquire"].return_value = ["__task_lock__"]

        # __task_lock__ doesn't grow blocked_resources, so loop terminates
        qs = ChainedQuerySet([[task1]])
        patched_modules["Task"].objects.filter.return_value = qs

        worker = _make_worker()
        result = worker.fetch_task()

        assert result is None
        overlap_excludes = qs.get_overlap_excludes()
        for excl in overlap_excludes:
            assert "__task_lock__" not in excl

    def test_returns_none_when_all_blocked(self, patched_modules):
        """When all tasks need the same blocked resource, returns None."""
        resource_a = "prn:rpm.repository:aaa"
        tasks = [_make_task(resources=[resource_a]) for _ in range(5)]

        patched_modules["extract"].return_value = ([resource_a], [])
        patched_modules["acquire"].return_value = [resource_a]

        # Batch 1: discover blocked resource. Batch 2: exclusion filters all → empty.
        qs = ChainedQuerySet([tasks, []])
        patched_modules["Task"].objects.filter.return_value = qs

        worker = _make_worker()
        result = worker.fetch_task()

        assert result is None
        # Only 1 Redis call — rest skipped by taken_exclusive
        assert patched_modules["acquire"].call_count == 1

    def test_claims_first_available(self, patched_modules):
        """Returns the first claimable task."""
        resource_a = "prn:rpm.repository:aaa"
        task1 = _make_task(resources=[resource_a])

        patched_modules["extract"].return_value = ([resource_a], [])
        patched_modules["acquire"].return_value = []

        qs = ChainedQuerySet([[task1]])
        claim_qs = MagicMock()
        claim_qs.update.return_value = 1
        patched_modules["Task"].objects.filter.side_effect = [qs, claim_qs]

        worker = _make_worker()
        result = worker.fetch_task()

        assert result is not None
        assert result.pk == task1.pk

    def test_empty_queue(self, patched_modules):
        """Returns None when no waiting tasks exist."""
        qs = ChainedQuerySet([[]])
        patched_modules["Task"].objects.filter.return_value = qs

        worker = _make_worker()
        result = worker.fetch_task()

        assert result is None
        patched_modules["acquire"].assert_not_called()

    def test_multiple_blocked_resources_accumulated(self, patched_modules):
        """blocked_resources accumulates across multiple acquire_locks failures."""
        resource_a = "prn:rpm.repository:aaa"
        resource_b = "prn:rpm.repository:bbb"
        resource_c = "prn:rpm.repository:ccc"

        task_a = _make_task(resources=[resource_a])
        task_b = _make_task(resources=[resource_b])
        task_c = _make_task(resources=[resource_c])

        patched_modules["extract"].side_effect = [
            ([resource_a], []),
            ([resource_b], []),
            ([resource_c], []),
        ]
        patched_modules["acquire"].side_effect = [
            [resource_a],  # task_a blocked
            [resource_b],  # task_b blocked → blocked_resources grows again → re-query
            [],  # task_c locks acquired
        ]

        # Batch 1: task_a blocked. Batch 2: task_b blocked. Batch 3: task_c claimable.
        qs = ChainedQuerySet(
            [
                [task_a],
                [task_b],
                [task_c],
            ]
        )
        claim_qs = MagicMock()
        claim_qs.update.return_value = 1

        def filter_side_effect(**kwargs):
            if "pk" in kwargs:
                return claim_qs
            return qs

        patched_modules["Task"].objects.filter = filter_side_effect

        worker = _make_worker()
        result = worker.fetch_task()

        assert result is not None
        assert result.pk == task_c.pk

        overlap_excludes = qs.get_overlap_excludes()
        assert len(overlap_excludes) >= 2
        # Second exclude should contain both resource_a and resource_b
        last_exclude = overlap_excludes[-1]
        assert resource_a in last_exclude
        assert resource_b in last_exclude

    def test_stops_when_no_new_blocked_resources(self, patched_modules):
        """Loop terminates when no new blocked resources are discovered
        (prevents infinite re-querying)."""
        resource_a = "prn:rpm.repository:aaa"

        task1 = _make_task(resources=[resource_a])
        task2 = _make_task(resources=[resource_a])

        patched_modules["extract"].return_value = ([resource_a], [])
        patched_modules["acquire"].return_value = [resource_a]

        # Batch 1: discover resource_a blocked. Batch 2: same resource_a blocked
        # again (no growth) → should stop, not loop forever.
        qs = ChainedQuerySet([[task1], [task2], []])
        patched_modules["Task"].objects.filter.return_value = qs

        worker = _make_worker()
        result = worker.fetch_task()

        assert result is None
        # Should have queried at most 2 batches (initial + one retry)
        assert qs.batch_index <= 2


@pytest.mark.django_db(transaction=True)
class TestFetchTaskIntegration:
    """Integration tests that run fetch_task() against real DB records
    with only Redis (acquire_locks) mocked."""

    @pytest.fixture(autouse=True)
    def setup_domain_and_worker(self):
        from datetime import timedelta

        from pulpcore.app.models import AppStatus, Domain
        from pulpcore.app.util import set_domain

        self.domain = Domain.objects.get_or_create(
            name="test-integration",
            defaults={"storage_class": "django.core.files.storage.FileSystemStorage"},
        )[0]
        set_domain(self.domain)

        self.app_status = AppStatus.objects.create(
            name="1@test-integration-worker",
            app_type="worker",
            versions={},
            ttl=timedelta(seconds=30),
        )

    def _create_task(self, resources, state="waiting"):
        from pulpcore.app.models import Task

        return Task.objects.create(
            state=state,
            name="test.task",
            logging_cid="test",
            reserved_resources_record=resources,
            pulp_domain=self.domain,
        )

    def _make_worker(self):
        from pulpcore.tasking.redis_worker import RedisWorker

        worker = object.__new__(RedisWorker)
        worker.ignored_task_ids = []
        worker.redis_conn = MagicMock()
        worker.name = self.app_status.name
        worker.app_status = self.app_status
        return worker

    @patch("pulpcore.tasking.redis_worker.acquire_locks")
    @patch("pulpcore.tasking.redis_worker.safe_release_task_locks")
    def test_skips_blocked_resource_claims_free_resource(self, mock_release, mock_acquire):
        """With 25 tasks needing blocked resource A and 1 task needing
        free resource B, fetch_task() should skip all A tasks and claim B."""
        resource_a = "prn:rpm.repository:blocked-repo"
        resource_b = "prn:rpm.repository:free-repo"

        for i in range(25):
            self._create_task([resource_a, "shared:prn:core.domain:ddd"])
        task_b = self._create_task([resource_b, "shared:prn:core.domain:ddd"])

        def acquire_side_effect(
            redis_conn, lock_owner, task_lock_key, exclusive_resources, shared_resources
        ):
            if resource_a in exclusive_resources:
                return [resource_a]
            return []

        mock_acquire.side_effect = acquire_side_effect

        worker = self._make_worker()
        result = worker.fetch_task()

        assert result is not None
        assert result.pk == task_b.pk
        assert result.app_lock == self.app_status

    @patch("pulpcore.tasking.redis_worker.acquire_locks")
    @patch("pulpcore.tasking.redis_worker.safe_release_task_locks")
    def test_returns_none_when_all_resources_blocked(self, mock_release, mock_acquire):
        """When every task needs a blocked resource, returns None."""
        resource_a = "prn:rpm.repository:blocked-repo"

        for i in range(10):
            self._create_task([resource_a, "shared:prn:core.domain:ddd"])

        mock_acquire.return_value = [resource_a]

        worker = self._make_worker()
        result = worker.fetch_task()

        assert result is None
        assert mock_acquire.call_count == 1

    @patch("pulpcore.tasking.redis_worker.acquire_locks")
    @patch("pulpcore.tasking.redis_worker.safe_release_task_locks")
    def test_multiple_blocked_resources_finds_free_task(self, mock_release, mock_acquire):
        """With tasks needing 3 different blocked resources and 1 task
        needing a free resource, fetch_task() finds the free one."""
        blocked = [
            "prn:rpm.repository:blocked-1",
            "prn:rpm.repository:blocked-2",
            "prn:rpm.repository:blocked-3",
        ]
        free = "prn:rpm.repository:free"

        for res in blocked:
            for _ in range(5):
                self._create_task([res, "shared:prn:core.domain:ddd"])
        task_free = self._create_task([free, "shared:prn:core.domain:ddd"])

        def acquire_side_effect(
            redis_conn, lock_owner, task_lock_key, exclusive_resources, shared_resources
        ):
            if any(r in blocked for r in exclusive_resources):
                return [r for r in exclusive_resources if r in blocked]
            return []

        mock_acquire.side_effect = acquire_side_effect

        worker = self._make_worker()
        result = worker.fetch_task()

        assert result is not None
        assert result.pk == task_free.pk

    @patch("pulpcore.tasking.redis_worker.acquire_locks")
    @patch("pulpcore.tasking.redis_worker.safe_release_task_locks")
    def test_fifo_order_preserved_for_free_resources(self, mock_release, mock_acquire):
        """Among tasks with free resources, FIFO order is preserved."""
        resource_blocked = "prn:rpm.repository:blocked"
        resource_free = "prn:rpm.repository:free"

        self._create_task([resource_blocked])
        task_first = self._create_task([resource_free])
        self._create_task([resource_free])

        def acquire_side_effect(
            redis_conn, lock_owner, task_lock_key, exclusive_resources, shared_resources
        ):
            if resource_blocked in exclusive_resources:
                return [resource_blocked]
            return []

        mock_acquire.side_effect = acquire_side_effect

        worker = self._make_worker()
        result = worker.fetch_task()

        assert result is not None
        assert result.pk == task_first.pk
