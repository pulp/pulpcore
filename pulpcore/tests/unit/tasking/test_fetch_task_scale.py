"""Scale test for fetch_task head-of-line blocking fix (issue #7900).

Asserts on actual database behavior to prove the fix is efficient:
1. The overlap operator (&&) appears in captured SQL
2. auto_explain PostgreSQL logs show Index Scan or Bitmap usage
3. Query count is bounded
4. acquire_locks calls are proportional to distinct blocked resources
"""

import subprocess
from datetime import timedelta
from unittest.mock import patch as mock_patch
from uuid import uuid4

import pytest
from django.db import connection

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

NUM_BLOCKED_RESOURCES = 50
NUM_BLOCKED_TASKS = 2000


@pytest.mark.django_db
def test_fetch_task_uses_db_exclusion_at_scale():
    """fetch_task() must use DB-level overlap exclusion at scale.

    Creates 2000 tasks across 50 blocked resources, then verifies:
    1. The && operator appears in captured SQL (DB-level exclusion)
    2. auto_explain shows Index Scan or Bitmap usage (not Seq Scan)
    3. Total DB query count is small (not O(log n) doubling)
    4. acquire_locks calls are proportional to distinct blocked resources
    """
    redis_conn = get_redis_connection()
    domain = Domain.objects.get(name="default")
    domain_shared = f"shared:prn:core.domain:{domain.pk}"
    test_id = uuid4().hex[:8]
    redis_keys = []

    AppStatus.objects._current_app_status = None
    app_status = AppStatus.objects.create(
        name=f"scale-{test_id}",
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

    # Block 50 distinct resources in Redis
    blocked_resources = [f"prn:test.scale-{test_id}.r:{i}" for i in range(NUM_BLOCKED_RESOURCES)]
    for res in blocked_resources:
        key = resource_to_lock_key(res)
        redis_conn.set(key, "other-worker")
        redis_keys.append(key)

    result = None
    try:
        # Create 2000 tasks distributed across the 50 blocked resources
        Task.objects.bulk_create(
            [
                Task(
                    state=TASK_STATES.WAITING,
                    name="pulpcore.app.tasks.test.sleep",
                    logging_cid=f"scale-{test_id}-{i}",
                    reserved_resources_record=[
                        blocked_resources[i % NUM_BLOCKED_RESOURCES],
                        domain_shared,
                    ],
                    pulp_domain=domain,
                )
                for i in range(NUM_BLOCKED_TASKS)
            ]
        )

        # Force statistics update so the query planner has accurate row counts
        cursor = connection.cursor()
        cursor.execute("ANALYZE core_task")

        # Count acquire_locks calls
        acquire_count = 0

        def counting_acquire(*args, **kwargs):
            nonlocal acquire_count
            acquire_count += 1
            return real_acquire(*args, **kwargs)

        # Mark log position BEFORE test so we only check new auto_explain entries
        subprocess.run(
            [
                "bash",
                "-c",
                "TODAY=$(date +%a); "
                "wc -l < /data/pgsql/log/postgresql-${TODAY}.log "
                "> /tmp/.scale_test_log_pos",
            ],
            capture_output=True,
        )

        # Capture DB queries during fetch_task
        connection.force_debug_cursor = True
        connection.queries_log.clear()

        with mock_patch(
            "pulpcore.tasking.redis_worker.acquire_locks",
            side_effect=counting_acquire,
        ):
            result = worker.fetch_task()

        captured_queries = list(connection.queries)
        connection.force_debug_cursor = False

        # === DB Query Assertions ===

        # 1. The overlap operator (&&) must appear in at least one query
        overlap_queries = [
            q for q in captured_queries if "&&" in q["sql"] and "core_task" in q["sql"]
        ]
        assert len(overlap_queries) > 0, (
            "NO OVERLAP QUERIES: fetch_task() did not use the && operator "
            "to exclude blocked resources at the DB level. "
            "Captured queries:\n"
            + "\n".join(q["sql"][:200] for q in captured_queries if "core_task" in q["sql"])
        )

        # 2. Total task queries should be small (not O(log n) doubling)
        task_select_queries = [
            q for q in captured_queries if "core_task" in q["sql"] and "SELECT" in q["sql"].upper()
        ]
        assert len(task_select_queries) <= 10, (
            f"TOO MANY DB QUERIES: {len(task_select_queries)} SELECT queries "
            f"on core_task. With DB-level exclusion, fetch_task() should need "
            f"a small number of queries, not {len(task_select_queries)}."
        )

        # 3. acquire_locks calls proportional to distinct resources
        assert acquire_count <= NUM_BLOCKED_RESOURCES * 2, (
            f"acquire_locks called {acquire_count} times for "
            f"{NUM_BLOCKED_RESOURCES} distinct resources -- re-scanning"
        )

        # 4. auto_explain log: verify an index was used during actual execution
        log_after = subprocess.run(
            [
                "bash",
                "-c",
                "TODAY=$(date +%a); "
                "tail -n +$(($(cat /tmp/.scale_test_log_pos 2>/dev/null || echo 1))) "
                "/data/pgsql/log/postgresql-${TODAY}.log",
            ],
            capture_output=True,
            text=True,
        ).stdout

        plan_lines = [
            line.strip()
            for line in log_after.split("\n")
            if "Scan" in line or "Index" in line or "Bitmap" in line
        ]
        index_used = any("Index Scan" in line or "Bitmap" in line for line in plan_lines)
        seq_scan_only = (
            all("Seq Scan" in line for line in plan_lines if "Scan" in line) if plan_lines else True
        )

        assert index_used and not seq_scan_only, (
            "NO INDEX USED: auto_explain shows the overlap query used "
            "Seq Scan instead of an index during actual execution.\n"
            "Plan lines from PostgreSQL log:\n" + "\n".join(plan_lines[:10])
        )

    finally:
        for key in redis_keys:
            redis_conn.delete(key)
        if result:
            safe_release_task_locks(result, lock_owner=worker.name)
            Task.objects.filter(pk=result.pk).update(app_lock=None, state=TASK_STATES.COMPLETED)
        Task.objects.filter(logging_cid__startswith=f"scale-{test_id}").delete()
        AppStatus.objects._current_app_status = None
        app_status.delete()
