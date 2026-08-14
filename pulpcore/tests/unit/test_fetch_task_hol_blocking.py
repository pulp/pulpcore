"""
Test for head-of-line blocking in RedisWorker.fetch_task().

Reproduces https://github.com/pulp/pulpcore/issues/7900

Scenario: Queue has many tasks with different blocked resources at the
head, followed by a task with a free resource. Without the fix,
fetch_task() re-scans from position 0 on each doubling iteration,
calling acquire_locks repeatedly on already-known-blocked resources.
With the fix, blocked resources are excluded at the DB level via the
GIN index, so each resource is tried at most once.
"""

import time
import uuid
from datetime import timedelta
from unittest.mock import patch as mock_patch

import pytest
import redis

from pulpcore.tasking.redis_locks import acquire_locks as real_acquire_locks


@pytest.mark.django_db
class TestFetchTaskHeadOfLineBlocking:
    @pytest.fixture(autouse=True)
    def setup(self):
        from pulpcore.app.models import AppStatus, Domain
        from pulpcore.app.util import set_domain

        try:
            self.redis_conn = redis.Redis(host="localhost", port=6379, decode_responses=True)
            self.redis_conn.ping()
        except redis.ConnectionError:
            pytest.skip("Redis not available")

        self.domain, _ = Domain.objects.get_or_create(
            name="default", defaults={"storage_class": "pulpcore.app.models.storage.FileSystem"}
        )
        set_domain(self.domain)

        AppStatus.objects._current_app_status = None
        self.app_status = AppStatus.objects.create(
            name=f"test-worker-{uuid.uuid4().hex[:8]}",
            app_type="worker",
            versions={},
            ttl=timedelta(seconds=30),
        )
        yield
        AppStatus.objects._current_app_status = None

    def _make_worker(self):
        from pulpcore.tasking.redis_worker import RedisWorker

        worker = object.__new__(RedisWorker)
        worker.ignored_task_ids = []
        worker.redis_conn = self.redis_conn
        worker.name = self.app_status.name
        worker.app_status = self.app_status
        return worker

    def _cleanup_task(self, task, worker):
        from pulpcore.app.models import Task
        from pulpcore.tasking.redis_locks import safe_release_task_locks

        safe_release_task_locks(task, lock_owner=worker.name)
        Task.objects.filter(pk=task.pk).update(app_lock=None, state="completed")

    def test_blocked_resource_exclusion_reduces_acquire_locks_calls(self):
        """
        With 100 tasks each having a DIFFERENT blocked resource at the
        queue head, and 1 task with a free resource behind them,
        fetch_task() should call acquire_locks at most once per unique
        resource (~101 calls).

        Without DB-level blocked-resource exclusion, the doubling
        algorithm re-queries from position 0 and re-calls acquire_locks
        on already-tried resources because taken_exclusive/taken_shared
        are reset on each iteration. This results in ~241 calls:
          batch 1 (20): 20 calls
          batch 2 (40 from 0): 40 calls (re-tries first 20)
          batch 3 (80 from 0): 80 calls (re-tries first 40)
          batch 4 (160 from 0): 101 calls (re-tries first 80)
        """
        from pulpcore.app.models import Task

        domain = self.domain
        domain_shared = f"shared:prn:core.domain:{domain.pk}"
        num_blocked = 100
        blocked_resources = []
        lock_keys = []

        for i in range(num_blocked):
            resource = f"prn:core.repository:{uuid.uuid4()}"
            blocked_resources.append(resource)
            lock_key = f"pulp:resource_lock:{resource}"
            lock_keys.append(lock_key)
            self.redis_conn.set(lock_key, "other-worker-holding-lock")

        free_resource = f"prn:core.repository:{uuid.uuid4()}"

        try:
            blocked_tasks = [
                Task(
                    state="waiting",
                    name="pulpcore.app.tasks.test.sleep",
                    logging_cid=f"blocked-{i}",
                    reserved_resources_record=[blocked_resources[i], domain_shared],
                    pulp_domain=domain,
                    enc_args=[0],
                    enc_kwargs={},
                )
                for i in range(num_blocked)
            ]
            Task.objects.bulk_create(blocked_tasks)

            time.sleep(0.01)

            free_task = Task.objects.create(
                state="waiting",
                name="pulpcore.app.tasks.test.sleep",
                logging_cid="free-task",
                reserved_resources_record=[free_resource, domain_shared],
                pulp_domain=domain,
                enc_args=[0],
                enc_kwargs={},
            )

            worker = self._make_worker()

            call_count = 0

            def counting_acquire(*args, **kwargs):
                nonlocal call_count
                call_count += 1
                return real_acquire_locks(*args, **kwargs)

            with mock_patch(
                "pulpcore.tasking.redis_worker.acquire_locks",
                side_effect=counting_acquire,
            ):
                result = worker.fetch_task()

            assert result is not None, "fetch_task() should find the free task"
            assert result.pk == free_task.pk, (
                f"Should claim the free task, got {result.logging_cid}"
            )

            # With DB-level exclusion, each blocked resource is tried at
            # most once: ~101 calls (100 failures + 1 success).
            # Without the fix, doubling + re-scanning causes ~241 calls.
            # Threshold at 120 gives margin while catching the regression.
            assert call_count <= 120, (
                f"acquire_locks called {call_count} times — expected <= 120. "
                f"With blocked-resource DB exclusion each resource is tried "
                f"once (~101 calls). The current count indicates the doubling "
                f"algorithm is re-scanning already-tried resources."
            )

            self._cleanup_task(result, worker)

        finally:
            for key in lock_keys:
                self.redis_conn.delete(key)
            Task.objects.filter(logging_cid__startswith="blocked-").delete()
            Task.objects.filter(logging_cid="free-task").delete()
