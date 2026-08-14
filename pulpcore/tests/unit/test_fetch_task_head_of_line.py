"""
Reproduce pulpcore#7900: head-of-line blocking in RedisWorker.fetch_task().

When many tasks at the queue head need resources that are locked by other
workers, fetch_task() should learn which resources are blocked and exclude
them from subsequent DB queries — not re-scan from position 0 each time.
"""

import pytest
import redis
from datetime import timedelta
from unittest.mock import patch as mock_patch

from pulpcore.app.models import AppStatus, Domain, Task
from pulpcore.tasking.redis_locks import acquire_locks as real_acquire, safe_release_task_locks
from pulpcore.tasking.redis_worker import RedisWorker


@pytest.mark.django_db
class TestFetchTaskHeadOfLineBlocking:

    @pytest.fixture(autouse=True)
    def setup(self):
        AppStatus.objects._current_app_status = None
        self.app_status = AppStatus.objects.create(
            name="test-worker",
            app_type="worker",
            versions={},
            ttl=timedelta(seconds=30),
        )

        self.redis_conn = redis.Redis(host="localhost", port=6379, decode_responses=True)

        self.worker = object.__new__(RedisWorker)
        self.worker.ignored_task_ids = []
        self.worker.redis_conn = self.redis_conn
        self.worker.name = self.app_status.name
        self.worker.app_status = self.app_status

        self.domain = Domain.objects.get(name="default")
        self.domain_shared = f"shared:prn:core.domain:{self.domain.pk}"

        yield

        Task.objects.filter(name="test.task").delete()
        for key in self.redis_conn.keys("pulp:resource_lock:*"):
            self.redis_conn.delete(key)
        for key in self.redis_conn.keys("task:*"):
            self.redis_conn.delete(key)
        AppStatus.objects._current_app_status = None

    def test_blocked_resources_excluded_from_subsequent_queries(self):
        """
        200 tasks each needing a different blocked exclusive resource, then
        1 task needing a free resource.

        Without the fix, the doubling loop re-scans from position 0 with
        reset taken-sets, calling acquire_locks ~501 times total.

        With the fix, blocked resources are excluded at the DB level so each
        batch returns only unseen tasks — ~201 acquire_locks calls.
        """
        num_blocked = 200
        blocked_lock_keys = []
        tasks = []

        for i in range(num_blocked):
            resource = f"prn:core.repository:aaaaaaaa-0000-0000-0000-{i:012d}"
            lock_key = f"pulp:resource_lock:{resource}"
            self.redis_conn.set(lock_key, "other-worker")
            blocked_lock_keys.append(lock_key)
            tasks.append(
                Task(
                    state="waiting",
                    name="test.task",
                    logging_cid=f"blocked-{i}",
                    reserved_resources_record=[resource, self.domain_shared],
                    pulp_domain=self.domain,
                    enc_args=[0],
                    enc_kwargs={},
                )
            )

        Task.objects.bulk_create(tasks)

        free_resource = "prn:core.repository:ffffffff-ffff-ffff-ffff-ffffffffffff"
        free_task = Task.objects.create(
            state="waiting",
            name="test.task",
            logging_cid="free-task",
            reserved_resources_record=[free_resource, self.domain_shared],
            pulp_domain=self.domain,
            enc_args=[0],
            enc_kwargs={},
        )

        call_count = 0

        def counting_acquire(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            return real_acquire(*args, **kwargs)

        with mock_patch(
            "pulpcore.tasking.redis_worker.acquire_locks",
            side_effect=counting_acquire,
        ):
            result = self.worker.fetch_task()

        if result:
            safe_release_task_locks(result, lock_owner=self.worker.name)
            Task.objects.filter(pk=result.pk).update(app_lock=None, state="completed")

        for key in blocked_lock_keys:
            self.redis_conn.delete(key)

        assert result is not None, "Worker failed to reach the free task behind 200 blocked tasks"
        assert result.pk == free_task.pk, (
            "Worker claimed a blocked task instead of the free task"
        )
        assert call_count <= 300, (
            f"acquire_locks called {call_count} times (expected <= 300). "
            f"The doubling loop re-scans blocked tasks from position 0 instead of "
            f"excluding known-blocked resources. "
            f"See https://github.com/pulp/pulpcore/issues/7900"
        )
