"""Tests for fetch_task() blocked-resource DB-level exclusion (issue #7900)."""

from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

import pytest

from pulpcore.app.models import AppStatus, Task
from pulpcore.constants import TASK_STATES
from pulpcore.tasking.redis_worker import FETCH_TASK_LIMIT, RedisWorker


def _create_waiting_task(resources=None, name="test.fetch_task"):
    return Task.objects.create(
        name=name,
        state=TASK_STATES.WAITING,
        logging_cid="",
        reserved_resources_record=resources,
    )


@pytest.fixture
def worker():
    """Build a minimal object with the attributes fetch_task() needs."""
    AppStatus.objects._current_app_status = None
    app_status = AppStatus.objects.create(
        name=f"test-worker-{uuid4()}", app_type="worker", versions={}
    )
    w = SimpleNamespace(
        redis_conn=None,
        name=app_status.name,
        ignored_task_ids=[],
        app_status=app_status,
    )
    yield w
    app_status.delete()
    AppStatus.objects._current_app_status = None


@pytest.mark.django_db
def test_blocked_resource_exclusion_reaches_free_tasks(worker):
    """When queue head is dominated by one blocked resource, fetch_task skips
    them at the DB level and claims a task with a free resource."""
    blocked_res = f"prn:core.repository:{uuid4()}"
    free_res = f"prn:core.repository:{uuid4()}"

    for _ in range(FETCH_TASK_LIMIT + 5):
        _create_waiting_task(resources=[blocked_res])

    free_task = _create_waiting_task(resources=[free_res])

    acquire_calls = []

    def mock_acquire(_conn, _owner, _task_key, exclusive, shared):
        acquire_calls.append(exclusive + shared)
        resources = exclusive + shared
        if any(r == blocked_res for r in resources):
            return [blocked_res.encode()]
        return []

    with patch("pulpcore.tasking.redis_worker.acquire_locks", side_effect=mock_acquire):
        result = RedisWorker.fetch_task(worker)

    assert result is not None
    assert result.pk == free_task.pk
    assert len(acquire_calls) <= FETCH_TASK_LIMIT + 1


@pytest.mark.django_db
def test_no_infinite_loop_all_blocked(worker):
    """When every task is blocked, fetch_task returns None without looping."""
    blocked_res = f"prn:core.repository:{uuid4()}"

    for _ in range(5):
        _create_waiting_task(resources=[blocked_res])

    def mock_acquire(_conn, _owner, _task_key, exclusive, shared):
        return [blocked_res.encode()]

    with patch("pulpcore.tasking.redis_worker.acquire_locks", side_effect=mock_acquire):
        result = RedisWorker.fetch_task(worker)

    assert result is None


@pytest.mark.django_db
def test_multiple_blocked_resources_excluded(worker):
    """Resources from multiple failed acquire_locks calls are all excluded."""
    res_a = f"prn:core.repository:{uuid4()}"
    res_b = f"prn:core.repository:{uuid4()}"
    free_res = f"prn:core.repository:{uuid4()}"

    for _ in range(10):
        _create_waiting_task(resources=[res_a])
    for _ in range(10):
        _create_waiting_task(resources=[res_b])

    free_task = _create_waiting_task(resources=[free_res])

    def mock_acquire(_conn, _owner, _task_key, exclusive, shared):
        resources = exclusive + shared
        if any(r == res_a for r in resources):
            return [res_a.encode()]
        if any(r == res_b for r in resources):
            return [res_b.encode()]
        return []

    with patch("pulpcore.tasking.redis_worker.acquire_locks", side_effect=mock_acquire):
        result = RedisWorker.fetch_task(worker)

    assert result is not None
    assert result.pk == free_task.pk


@pytest.mark.django_db
def test_task_lock_not_added_to_blocked_resources(worker):
    """__task_lock__ from acquire_locks is not treated as a resource exclusion."""
    res_a = f"prn:core.repository:{uuid4()}"
    res_b = f"prn:core.repository:{uuid4()}"

    _create_waiting_task(resources=[res_a])
    _create_waiting_task(resources=[res_b])

    call_count = [0]

    def mock_acquire(_conn, _owner, _task_key, exclusive, shared):
        call_count[0] += 1
        if call_count[0] == 1:
            return [b"__task_lock__"]
        return []

    with patch("pulpcore.tasking.redis_worker.acquire_locks", side_effect=mock_acquire):
        result = RedisWorker.fetch_task(worker)

    assert result is not None
