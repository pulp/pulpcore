"""Reproduction test for RedisWorker fetch_task() head-of-line blocking (issue #7900).

When many waiting tasks need the same blocked exclusive resource, fetch_task()
should skip them at the DB level and find tasks for free resources without
excessive acquire_locks calls.
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
    resource_to_lock_key,
    safe_release_task_locks,
)
from pulpcore.tasking.redis_worker import RedisWorker


@pytest.mark.django_db
def test_fetch_task_skips_blocked_resources():
    """fetch_task() must skip tasks for blocked resources and find free ones.

    Reproduces issue #7900: when many tasks need a blocked exclusive resource,
    fetch_task() should use DB-level exclusion to skip them and find tasks
    for free resources, without excessive acquire_locks calls.

    With the bug (no DB-level exclusion):
      - The doubling algorithm (20->40->80->160->320) re-scans from position 0
        each iteration, calling acquire_locks once per iteration for the first
        blocked task. Total: ~6 acquire_locks calls for 200 blocked tasks.

    With the fix (DB-level exclusion via __overlap):
      - After the first acquire_locks failure, the blocked resource is excluded
        from subsequent DB queries. The free-resource task is found directly.
        Total: 2 acquire_locks calls.
    """
    redis_conn = get_redis_connection()
    domain = Domain.objects.get(name="default")
    domain_shared = f"shared:prn:core.domain:{domain.pk}"
    test_id = uuid4().hex[:8]
    redis_keys = []

    AppStatus.objects._current_app_status = None
    app_status = AppStatus.objects.create(
        name=f"test-hol-{test_id}",
        app_type="worker",
        versions={},
        ttl=timedelta(seconds=30),
    )

    worker = object.__new__(RedisWorker)
    worker.ignored_task_ids = list(
        Task.objects.filter(state=TASK_STATES.WAITING, app_lock=None).values_list(
            "pk", flat=True
        )
    )
    worker.redis_conn = redis_conn
    worker.name = app_status.name
    worker.app_status = app_status

    # Block one resource in Redis (simulates another worker holding it)
    blocked_resource = f"prn:test.hol-{test_id}:blocked"
    blocked_key = resource_to_lock_key(blocked_resource)
    redis_conn.set(blocked_key, "other-worker")
    redis_keys.append(blocked_key)

    free_resource = f"prn:test.hol-{test_id}:free"

    result = None
    try:
        # Create 200 tasks needing the blocked resource (fill the queue head)
        Task.objects.bulk_create(
            [
                Task(
                    state=TASK_STATES.WAITING,
                    name="pulpcore.app.tasks.test.sleep",
                    logging_cid=f"hol-{test_id}-blocked-{i}",
                    reserved_resources_record=[blocked_resource, domain_shared],
                    pulp_domain=domain,
                )
                for i in range(200)
            ]
        )

        # Create 1 task needing a free resource (last in FIFO order)
        Task.objects.bulk_create(
            [
                Task(
                    state=TASK_STATES.WAITING,
                    name="pulpcore.app.tasks.test.sleep",
                    logging_cid=f"hol-{test_id}-free",
                    reserved_resources_record=[free_resource, domain_shared],
                    pulp_domain=domain,
                )
            ]
        )

        # Count acquire_locks calls during fetch_task
        acquire_count = 0

        def counting_acquire(*args, **kwargs):
            nonlocal acquire_count
            acquire_count += 1
            return real_acquire(*args, **kwargs)

        with mock_patch(
            "pulpcore.tasking.redis_worker.acquire_locks",
            side_effect=counting_acquire,
        ):
            result = worker.fetch_task()

        # The free-resource task must be found
        assert result is not None, (
            "fetch_task() returned None -- failed to find the free-resource task "
            "behind 200 blocked tasks"
        )
        assert f"hol-{test_id}-free" in result.logging_cid, (
            f"fetch_task() returned wrong task: {result.logging_cid}"
        )

        # With DB-level exclusion, acquire_locks should be called at most 3 times
        # (1 for the blocked resource + 1 for the free resource + margin).
        # Without the fix, the doubling algorithm calls it ~6 times.
        assert acquire_count <= 3, (
            f"acquire_locks called {acquire_count} times -- fetch_task() is "
            f"re-scanning blocked resources instead of excluding them at the DB level"
        )

    finally:
        for key in redis_keys:
            redis_conn.delete(key)
        if result:
            safe_release_task_locks(result, lock_owner=worker.name)
            Task.objects.filter(pk=result.pk).update(
                app_lock=None, state=TASK_STATES.COMPLETED
            )
        Task.objects.filter(logging_cid__startswith=f"hol-{test_id}").delete()
        AppStatus.objects._current_app_status = None
        app_status.delete()
