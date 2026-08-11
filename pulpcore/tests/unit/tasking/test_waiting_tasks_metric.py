from datetime import timedelta
from uuid import uuid4

import pytest
from django.utils import timezone

from pulpcore.app.models import Task
from pulpcore.constants import TASK_STATES
from pulpcore.tasking.redis_worker import count_waiting_tasks_for_metric


@pytest.fixture
def frozen_clock(monkeypatch):
    """Move timezone.now() forward so freshly inserted tasks pass the 5s age cutoff.

    Task.pulp_created is set by a DB trigger (clock_timestamp) and cannot be updated,
    so tests age tasks by advancing the metric's cutoff clock instead.
    """

    class _Clock:
        def __init__(self):
            self.now = timezone.now()

        def __call__(self):
            return self.now

        def advance(self, seconds):
            self.now += timedelta(seconds=seconds)

    clock = _Clock()
    monkeypatch.setattr(timezone, "now", clock)
    return clock


def _create_task(*, state, resources=None, name="test.waiting_tasks_metric"):
    return Task.objects.create(
        name=name,
        state=state,
        logging_cid="",
        reserved_resources_record=resources,
    )


@pytest.mark.django_db
def test_waiting_tasks_metric_resource_contention(frozen_clock):
    """Exclusive holder + exclusive/shared waiters on same resource → count 1."""
    exclusive_resource = str(uuid4())

    _create_task(state=TASK_STATES.RUNNING, resources=[exclusive_resource])
    for _ in range(5):
        _create_task(state=TASK_STATES.WAITING, resources=[exclusive_resource])
    for _ in range(5):
        _create_task(
            state=TASK_STATES.WAITING,
            resources=[f"shared:{exclusive_resource}"],
        )

    frozen_clock.advance(6)
    assert count_waiting_tasks_for_metric() == 1


@pytest.mark.django_db
def test_waiting_tasks_metric_two_exclusive_lanes(frozen_clock):
    """Two independent exclusive lanes with waiters → count 2."""
    resource_a = str(uuid4())
    resource_b = str(uuid4())

    _create_task(state=TASK_STATES.RUNNING, resources=[resource_a])
    for _ in range(5):
        _create_task(state=TASK_STATES.WAITING, resources=[resource_a])

    _create_task(state=TASK_STATES.WAITING, resources=[resource_b])
    for _ in range(5):
        _create_task(state=TASK_STATES.WAITING, resources=[resource_b])

    frozen_clock.advance(6)
    assert count_waiting_tasks_for_metric() == 2


@pytest.mark.django_db
def test_waiting_tasks_metric_shared_resources_can_run_together(frozen_clock):
    """N shared-only tasks on same resource → count N (not 1)."""
    shared_resource = str(uuid4())
    shared_task_count = 5

    for _ in range(shared_task_count):
        _create_task(
            state=TASK_STATES.WAITING,
            resources=[f"shared:{shared_resource}"],
        )

    frozen_clock.advance(6)
    assert count_waiting_tasks_for_metric() == shared_task_count


@pytest.mark.django_db
def test_waiting_tasks_metric_fifo_blocks_indirect_resources(frozen_clock):
    """T1(A,B) running, T2(B,C) and T3(C) waiting → count 1 (FIFO), not 2."""
    resource_a = str(uuid4())
    resource_b = str(uuid4())
    resource_c = str(uuid4())

    # Insert order sets pulp_created via clock_timestamp(); keep create order FIFO.
    _create_task(state=TASK_STATES.RUNNING, resources=[resource_a, resource_b])
    _create_task(state=TASK_STATES.WAITING, resources=[resource_b, resource_c])
    _create_task(state=TASK_STATES.WAITING, resources=[resource_c])

    frozen_clock.advance(6)
    assert count_waiting_tasks_for_metric() == 1


@pytest.mark.django_db
def test_waiting_tasks_metric_ignores_young_tasks(frozen_clock):
    """Tasks newer than the five-second cutoff are not counted."""
    resource = str(uuid4())

    _create_task(state=TASK_STATES.WAITING, resources=[resource])
    frozen_clock.advance(1)

    assert count_waiting_tasks_for_metric() == 0


@pytest.mark.django_db
def test_waiting_tasks_metric_ignores_finished_tasks(frozen_clock):
    """Completed/canceled/failed tasks do not contribute to the count."""
    resource = str(uuid4())

    for state in (TASK_STATES.COMPLETED, TASK_STATES.CANCELED, TASK_STATES.FAILED):
        _create_task(state=state, resources=[resource])

    frozen_clock.advance(6)
    assert count_waiting_tasks_for_metric() == 0
