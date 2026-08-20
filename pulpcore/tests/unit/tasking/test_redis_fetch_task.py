"""Unit tests for RedisWorker.fetch_task batch expansion."""

import time
from uuid import uuid4

import pytest

from pulpcore.app.models import AppStatus, Task
from pulpcore.constants import TASK_STATES
from pulpcore.tasking.redis_worker import RedisWorker


def _waiting_task(resource):
    return Task.objects.create(
        state=TASK_STATES.WAITING,
        name="pulpcore.app.tasks.test.sleep",
        logging_cid=str(uuid4()),
        reserved_resources_record=[resource],
    )


@pytest.mark.django_db
def test_fetch_task_beyond_initial_batch(monkeypatch):
    """Blocked tasks filling the first fetch batch must not hide a later runnable task.

    Replaces the functional test that slept 60s and queued 25 tasks so a live
    RedisWorker would double FETCH_TASK_LIMIT.
    """
    monkeypatch.setattr(AppStatus.objects, "_current_app_status", None)
    monkeypatch.setattr("pulpcore.tasking.redis_worker.FETCH_TASK_LIMIT", 3)

    blocked_resource = f"exclusive:{uuid4()}"
    other_resource = f"exclusive:{uuid4()}"

    def acquire_locks(_conn, _name, _task_lock_key, exclusive_resources, _shared_resources):
        if blocked_resource in exclusive_resources:
            return [blocked_resource]
        return []

    monkeypatch.setattr("pulpcore.tasking.redis_worker.acquire_locks", acquire_locks)

    worker = RedisWorker.__new__(RedisWorker)
    worker.ignored_task_ids = []
    worker.name = f"test-worker-{uuid4()}"
    worker.app_status = AppStatus.objects.create(app_type="worker", name=worker.name)
    worker.redis_conn = object()

    for _ in range(4):
        _waiting_task(blocked_resource)
    # Task.pulp_created cannot be updated (DB trigger); sleep so this sorts after the batch.
    time.sleep(0.05)
    runnable = _waiting_task(other_resource)

    fetched = worker.fetch_task()

    assert fetched is not None
    assert fetched.pk == runnable.pk
    runnable.refresh_from_db()
    assert runnable.app_lock_id == worker.app_status.pk
