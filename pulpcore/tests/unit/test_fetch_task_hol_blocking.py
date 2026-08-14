"""
Tests for RedisWorker.fetch_task() head-of-line blocking fix.

Verifies that fetch_task() efficiently skips past tasks blocked on
the same resource, reaching tasks with free resources without
excessive acquire_locks calls or DB queries.

GitHub issue: https://github.com/pulp/pulpcore/issues/7900
"""

from datetime import timedelta
from unittest.mock import patch as mock_patch

import pytest
import redis

from pulpcore.app.models import AppStatus, Domain, Task
from pulpcore.app.util import set_domain
from pulpcore.constants import TASK_STATES
from pulpcore.tasking.redis_locks import (
    REDIS_LOCK_PREFIX,
    acquire_locks as real_acquire_locks,
    safe_release_task_locks,
)
from pulpcore.tasking.redis_worker import RedisWorker


BLOCKED_RESOURCE = "prn:rpm.repository:blocked-repo-uuid"
FREE_RESOURCE = "prn:python.repository:free-repo-uuid"


@pytest.mark.django_db
class TestFetchTaskHeadOfLineBlocking:
    @pytest.fixture(autouse=True)
    def setup(self):
        AppStatus.objects._current_app_status = None
        self.domain = Domain.objects.get(name="default")
        set_domain(self.domain)
        self.domain_shared = f"shared:prn:core.domain:{self.domain.pk}"

        self.app_status = AppStatus.objects.create(
            name="test-worker-hol",
            app_type="worker",
            versions={},
            ttl=timedelta(seconds=30),
        )

        self.redis_conn = redis.Redis(
            host="localhost", port=6379, decode_responses=True
        )

        self.worker = object.__new__(RedisWorker)
        self.worker.ignored_task_ids = []
        self.worker.redis_conn = self.redis_conn
        self.worker.name = self.app_status.name
        self.worker.app_status = self.app_status
        self.worker.versions = {}

        yield

        self._cleanup_redis()
        Task.objects.filter(logging_cid__startswith="hol-test-").delete()
        self.app_status.delete()
        AppStatus.objects._current_app_status = None

    def _cleanup_redis(self):
        for key in self.redis_conn.keys("pulp:resource_lock:*"):
            self.redis_conn.delete(key)
        for key in self.redis_conn.keys("task:*"):
            self.redis_conn.delete(key)

    def _create_tasks(self, resource, count, cid_prefix):
        tasks = [
            Task(
                state=TASK_STATES.WAITING,
                name="pulpcore.app.tasks.test.sleep",
                logging_cid=f"hol-test-{cid_prefix}-{i}",
                reserved_resources_record=[resource, self.domain_shared],
                pulp_domain=self.domain,
                enc_args=[0],
                enc_kwargs={},
            )
            for i in range(count)
        ]
        Task.objects.bulk_create(tasks)
        return tasks

    def _lock_resource_in_redis(self, resource):
        lock_key = f"{REDIS_LOCK_PREFIX}{resource}"
        self.redis_conn.set(lock_key, "other-worker-holding-lock")

    def _unlock_resource_in_redis(self, resource):
        lock_key = f"{REDIS_LOCK_PREFIX}{resource}"
        self.redis_conn.delete(lock_key)

    def test_fetch_task_finds_free_resource_efficiently(self):
        """
        When the queue head has many tasks blocked on one resource,
        fetch_task should find tasks with free resources without
        calling acquire_locks once per doubling iteration.

        With 100 blocked tasks (5 doubling iterations needed) and
        5 free tasks, the fix should need at most 3 acquire_locks
        calls (1 for blocked resource + 1 for free + 1 margin),
        while the original code needs 5+ (1 per doubling + 1 for free).
        """
        self._create_tasks(BLOCKED_RESOURCE, 100, "blocked")
        self._create_tasks(FREE_RESOURCE, 5, "free")

        self._lock_resource_in_redis(BLOCKED_RESOURCE)

        acquire_count = 0

        def counting_acquire(*args, **kwargs):
            nonlocal acquire_count
            acquire_count += 1
            return real_acquire_locks(*args, **kwargs)

        with mock_patch(
            "pulpcore.tasking.redis_worker.acquire_locks",
            side_effect=counting_acquire,
        ):
            result = self.worker.fetch_task()

        assert result is not None, (
            "fetch_task must find a task with a free resource"
        )
        assert FREE_RESOURCE in result.reserved_resources_record, (
            f"Expected task for {FREE_RESOURCE}, got {result.reserved_resources_record}"
        )
        assert acquire_count <= 3, (
            f"acquire_locks called {acquire_count} times — "
            f"fetch_task is not skipping blocked resources efficiently. "
            f"Expected <= 3 (1 blocked discovery + 1 free claim + margin), "
            f"got {acquire_count} (indicates per-doubling re-scanning)."
        )

        safe_release_task_locks(result, lock_owner=self.worker.name)
        Task.objects.filter(pk=result.pk).update(
            app_lock=None, state=TASK_STATES.COMPLETED
        )
