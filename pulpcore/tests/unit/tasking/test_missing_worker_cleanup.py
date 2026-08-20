"""Unit tests for missing-worker cleanup."""

from datetime import timedelta
from uuid import uuid4

import pytest
from django.conf import settings
from django.utils import timezone

from pulpcore.app.models import AppStatus, Task
from pulpcore.constants import TASK_STATES
from pulpcore.tasking.worker import PulpcoreWorker


@pytest.mark.django_db
def test_missing_worker_cleanup_fails_abandoned_task(monkeypatch):
    """
    Surviving workers should fail tasks abandoned by a missing worker.

    Mirrors the functional test_worker_cleanup_on_missing_worker path without
    waiting on the heartbeat/cleanup interval.
    """
    monkeypatch.setattr(AppStatus.objects, "_current_app_status", None)
    dead_worker = AppStatus.objects.create(app_type="worker", name=f"dead-worker-{uuid4()}")
    AppStatus.objects.filter(pk=dead_worker.pk).update(
        last_heartbeat=timezone.now() - timedelta(seconds=settings.WORKER_TTL + 60)
    )
    dead_worker.refresh_from_db()
    assert dead_worker.missing

    resource = f"exclusive:{uuid4()}"
    task = Task.objects.create(
        state=TASK_STATES.RUNNING,
        name="pulpcore.app.tasks.test.sleep",
        logging_cid=str(uuid4()),
        app_lock=dead_worker,
        unblocked_at=timezone.now(),
        started_at=timezone.now(),
        reserved_resources_record=[resource],
    )

    monkeypatch.setattr(AppStatus.objects, "_current_app_status", None)
    survivor = PulpcoreWorker()

    # Drop the missing worker record (nulls task.app_lock via SET_NULL).
    survivor.app_worker_cleanup()
    task.refresh_from_db()
    assert task.app_lock_id is None
    assert not AppStatus.objects.filter(pk=dead_worker.pk).exists()

    # Pick up the orphaned RUNNING task and mark it failed.
    survivor.handle_unblocked_tasks()
    task.refresh_from_db()
    assert task.state == TASK_STATES.FAILED
    assert task.error is not None
    reason = task.error.get("reason", "").lower()
    assert "worker" in reason and "missing" in reason
