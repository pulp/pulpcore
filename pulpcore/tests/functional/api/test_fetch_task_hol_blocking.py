"""
Tests for RedisWorker.fetch_task() head-of-line blocking (GitHub #7900).

When the task queue has thousands of tasks needing the same blocked resource,
workers should still be able to reach tasks for free resources further down
the queue efficiently, without scanning all blocked tasks via repeated
doubling queries.

These are functional tests — they use real PostgreSQL, real Redis, and real
Task records. No mocking of system components.
"""

import os
from datetime import timedelta
from uuid import uuid4

import pytest
import redis as redis_lib

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "pulpcore.app.settings")


@pytest.fixture
def worker_env():
    """Create a test RedisWorker without starting a real worker process."""
    from pulpcore.app.models import AppStatus, Domain, Task
    from pulpcore.app.util import set_domain
    from pulpcore.tasking.redis_worker import RedisWorker

    domain = Domain.objects.get(name="default")
    set_domain(domain)

    AppStatus.objects._current_app_status = None
    app_status = AppStatus.objects.create(
        name=f"test-hol-{uuid4()}",
        app_type="worker",
        versions={},
        ttl=timedelta(seconds=30),
    )

    redis_conn = redis_lib.Redis(host="localhost", port=6379, decode_responses=True)
    worker = object.__new__(RedisWorker)
    worker.ignored_task_ids = []
    worker.redis_conn = redis_conn
    worker.name = app_status.name
    worker.app_status = app_status

    yield {
        "domain": domain,
        "worker": worker,
        "redis_conn": redis_conn,
        "Task": Task,
        "app_status": app_status,
    }

    AppStatus.objects._current_app_status = None
    app_status.delete()


@pytest.mark.django_db
def test_fetch_task_skips_blocked_resource_queue(worker_env):
    """
    With 1000 tasks needing a blocked resource and 1 task needing a free
    resource, fetch_task() must find the free task efficiently.

    The old algorithm doubles its query window (20 -> 40 -> ... -> 1280),
    requiring 8 acquire_locks calls and fetching ~2500 DB rows total.

    The fix should find the free task in <= 5 acquire_locks calls by
    excluding tasks needing known-blocked resources at the DB level.
    """
    from unittest.mock import patch as mock_patch

    from pulpcore.tasking.redis_locks import (
        acquire_locks as real_acquire,
    )
    from pulpcore.tasking.redis_locks import (
        safe_release_task_locks,
    )

    Task = worker_env["Task"]
    domain = worker_env["domain"]
    worker = worker_env["worker"]
    redis_conn = worker_env["redis_conn"]

    blocked_resource = f"prn:core.repository:{uuid4()}"
    free_resource = f"prn:core.repository:{uuid4()}"
    shared_domain = f"shared:prn:core.domain:{domain.name}"

    # Simulate another worker holding an exclusive lock on the blocked resource
    lock_key = f"pulp:resource_lock:{blocked_resource}"
    redis_conn.set(lock_key, "other-worker-holding-lock")

    try:
        # Create 1000 tasks needing the blocked resource (queue head)
        blocked_cids = [f"hol-blocked-{i}" for i in range(1000)]
        Task.objects.bulk_create(
            [
                Task(
                    state="waiting",
                    name="pulpcore.app.tasks.test.sleep",
                    logging_cid=cid,
                    reserved_resources_record=[blocked_resource, shared_domain],
                    pulp_domain=domain,
                    enc_args=[0],
                    enc_kwargs={},
                )
                for cid in blocked_cids
            ]
        )

        # Create 1 task needing a free resource (queue tail)
        free_task = Task.objects.create(
            state="waiting",
            name="pulpcore.app.tasks.test.sleep",
            logging_cid="hol-free-task",
            reserved_resources_record=[free_resource, shared_domain],
            pulp_domain=domain,
            enc_args=[0],
            enc_kwargs={},
        )

        # Count acquire_locks calls to measure efficiency
        call_count = [0]

        def counting_acquire(*args, **kwargs):
            call_count[0] += 1
            return real_acquire(*args, **kwargs)

        with mock_patch(
            "pulpcore.tasking.redis_worker.acquire_locks",
            side_effect=counting_acquire,
        ):
            result = worker.fetch_task()

        # The free task must be found
        assert result is not None, (
            "fetch_task() could not find the free task behind 1000 blocked tasks"
        )
        assert result.pk == free_task.pk, (
            f"fetch_task() returned wrong task: {result.logging_cid} (expected hol-free-task)"
        )

        # Efficiency gate: with blocked-resource DB exclusion, fetch_task
        # needs at most ~2-3 acquire_locks calls (1 to discover the blocked
        # resource, 1 to claim the free task). The old doubling algorithm
        # needs 8 calls for 1000 blocked tasks. Threshold of 5 clearly
        # separates the two.
        assert call_count[0] <= 5, (
            f"fetch_task() made {call_count[0]} acquire_locks calls to find "
            f"the free task behind 1000 blocked tasks — expected <= 5 with "
            f"blocked-resource DB exclusion (old algorithm would need ~8)"
        )

        # Cleanup the claimed task
        safe_release_task_locks(result, lock_owner=worker.name)
        Task.objects.filter(pk=result.pk).update(app_lock=None, state="completed")

    finally:
        redis_conn.delete(lock_key)
        Task.objects.filter(logging_cid__startswith="hol-blocked-").delete()
        Task.objects.filter(logging_cid="hol-free-task").delete()
