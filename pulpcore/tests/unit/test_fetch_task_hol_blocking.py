"""Unit tests for RedisWorker fetch_task() head-of-line blocking (issue #7900).

Tests exercise the real fetch_task() method against real PostgreSQL and Redis.
No mocking of system components — only acquire_locks is wrapped to count calls
(the real implementation is still called underneath).
"""

from datetime import timedelta
from unittest.mock import patch as mock_patch
from uuid import uuid4

import pytest

from pulpcore.app.models import AppStatus, Domain, Task
from pulpcore.app.redis_connection import get_redis_connection
from pulpcore.constants import TASK_STATES
from pulpcore.tasking.redis_locks import (
    acquire_locks as real_acquire,
)
from pulpcore.tasking.redis_locks import (
    resource_to_lock_key,
    safe_release_task_locks,
)
from pulpcore.tasking.redis_worker import RedisWorker


def _redis_available():
    """Check if Redis is reachable (not whether WORKER_TYPE is redis)."""
    try:
        conn = get_redis_connection()
        if conn is None:
            import redis as redis_lib

            conn = redis_lib.Redis(host="localhost", port=6379, decode_responses=True)
        conn.ping()
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not _redis_available(),
    reason="Redis is not available",
)


NUM_BLOCKED_RESOURCES = 10
NUM_BLOCKED_TASKS_PER_RESOURCE = 20
FREE_RESOURCE_SUFFIX = "free"


@pytest.fixture
def redis_conn():
    """Get a real Redis connection."""
    conn = get_redis_connection()
    if conn is None:
        import redis as redis_lib

        conn = redis_lib.Redis(host="localhost", port=6379, decode_responses=True)
    return conn


@pytest.fixture
def test_worker(redis_conn):
    """Create a test RedisWorker without starting a real worker process."""
    test_id = uuid4().hex[:8]
    AppStatus.objects._current_app_status = None
    app_status = AppStatus.objects.create(
        name=f"test-hol-{test_id}",
        app_type="worker",
        versions={},
        ttl=timedelta(seconds=30),
    )

    worker = object.__new__(RedisWorker)
    worker.ignored_task_ids = list(
        Task.objects.filter(state=TASK_STATES.WAITING, app_lock=None).values_list("pk", flat=True)
    )
    worker.redis_conn = redis_conn
    worker.name = app_status.name
    worker.app_status = app_status

    yield worker

    AppStatus.objects._current_app_status = None
    app_status.delete()


@pytest.mark.django_db
def test_fetch_task_skips_blocked_resources_efficiently(redis_conn, test_worker):
    """fetch_task() should call acquire_locks once per distinct blocked resource, not per task."""
    domain = Domain.objects.get(name="default")
    domain_shared = f"shared:prn:core.domain:{domain.pk}"
    test_id = uuid4().hex[:8]
    redis_keys = []

    # Lock resources in Redis to simulate them being held by another worker
    blocked_resources = [f"prn:test.hol-{test_id}.r:{i}" for i in range(NUM_BLOCKED_RESOURCES)]
    for res in blocked_resources:
        key = resource_to_lock_key(res)
        redis_conn.set(key, "other-worker-holding-lock")
        redis_keys.append(key)

    # Create tasks on blocked resources (200 total)
    num_blocked_tasks = NUM_BLOCKED_RESOURCES * NUM_BLOCKED_TASKS_PER_RESOURCE
    Task.objects.bulk_create(
        [
            Task(
                state=TASK_STATES.WAITING,
                name="pulpcore.app.tasks.test.sleep",
                logging_cid=f"hol-{test_id}-blocked-{i}",
                reserved_resources_record=[
                    blocked_resources[i % NUM_BLOCKED_RESOURCES],
                    domain_shared,
                ],
                pulp_domain=domain,
            )
            for i in range(num_blocked_tasks)
        ]
    )

    # Create ONE task on a free resource (not blocked in Redis)
    free_resource = f"prn:test.hol-{test_id}.r:{FREE_RESOURCE_SUFFIX}"
    free_task_obj = Task.objects.create(
        state=TASK_STATES.WAITING,
        name="pulpcore.app.tasks.test.sleep",
        logging_cid=f"hol-{test_id}-free",
        reserved_resources_record=[free_resource, domain_shared],
        pulp_domain=domain,
    )

    result = None
    acquire_count = 0

    def counting_acquire(*args, **kwargs):
        nonlocal acquire_count
        acquire_count += 1
        return real_acquire(*args, **kwargs)

    with mock_patch(
        "pulpcore.tasking.redis_worker.acquire_locks",
        side_effect=counting_acquire,
    ):
        result = test_worker.fetch_task()

    assert result is not None, (
        f"fetch_task() returned None — failed to find the free task among "
        f"{num_blocked_tasks} blocked tasks. acquire_locks was called "
        f"{acquire_count} times."
    )

    assert result.pk == free_task_obj.pk, (
        f"fetch_task() claimed task {result.logging_cid} instead of the free "
        f"task {free_task_obj.logging_cid}"
    )

    assert acquire_count == NUM_BLOCKED_RESOURCES + 1, (
        f"acquire_locks called {acquire_count} times, "
        f"expected {NUM_BLOCKED_RESOURCES + 1} "
        f"({NUM_BLOCKED_RESOURCES} blocked + 1 free)"
    )

    # Cleanup Redis keys (DB is rolled back by pytest-django)
    for key in redis_keys:
        redis_conn.delete(key)
    if result:
        safe_release_task_locks(result, lock_owner=test_worker.name)
