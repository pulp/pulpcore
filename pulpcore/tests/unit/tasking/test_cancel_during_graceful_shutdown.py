"""
Unit tests for task cancellation while a worker is shutting down gracefully.

A graceful shutdown (SIGTERM/SIGHUP) sets ``task_grace_timeout`` to ``None`` so the worker waits
indefinitely for the in-flight task to finish. An explicit cancellation of that task must still
abort it (SIGUSR1 to the task process); previously the cancellation reused
``task_grace_timeout`` as its kill deadline, so it waited forever too and the worker deadlocked,
heartbeating and holding the task's resource locks.
"""

import signal
from datetime import timedelta
from unittest import mock

import pytest

from pulpcore.constants import TASK_STATES
from pulpcore.tasking import redis_worker as redis_worker_module
from pulpcore.tasking import worker as worker_module

MAX_LOOP_ITERATIONS = 50


class FakeProcess:
    """Stand-in for the task ``multiprocessing.Process``; it only exits once it gets SIGUSR1."""

    def __init__(self, *args, **kwargs):
        self.pid = 4242
        self.sentinel = object()
        self.alive = True
        self.exitcode = None

    def start(self):
        pass

    def is_alive(self):
        return self.alive

    def join(self):
        pass

    def finish(self, exitcode=0):
        self.alive = False
        self.exitcode = exitcode


class Harness:
    """Patches the process/select/kill machinery used by ``supervise_task``."""

    def __init__(self, monkeypatch, module, on_first_select=None, finish_after=None):
        self.process = None
        self.kills = []
        self.select_calls = 0
        self.on_first_select = on_first_select
        self.finish_after = finish_after

        def make_process(*args, **kwargs):
            self.process = FakeProcess()
            return self.process

        def fake_kill(pid, sig):
            assert pid == self.process.pid
            self.kills.append(sig)
            if sig == signal.SIGUSR1:
                self.process.finish(exitcode=0)

        def fake_select(rlist, wlist, xlist, timeout=None):
            self.select_calls += 1
            if self.select_calls > MAX_LOOP_ITERATIONS:
                raise AssertionError("supervise_task never let the task process exit (deadlock)")
            if self.select_calls == 1 and self.on_first_select:
                self.on_first_select()
            if self.finish_after and self.select_calls >= self.finish_after:
                self.process.finish(exitcode=0)
            return ([self.process.sentinel] if not self.process.alive else [], [], [])

        monkeypatch.setattr(module, "Process", make_process)
        monkeypatch.setattr(module.os, "kill", fake_kill)
        monkeypatch.setattr(module.select, "select", fake_select)
        monkeypatch.setattr(module, "connection", mock.MagicMock())


def _make_task():
    task = mock.MagicMock()
    task.pk = "01a1841c-b360-7f5d-adb6-4ee443942c8e"
    task.pulp_domain.name = "default"
    task.reserved_resources_record = None
    return task


def _pulpcore_worker(graceful_shutdown):
    worker = object.__new__(worker_module.PulpcoreWorker)
    worker.sentinel = -1
    worker.heartbeat_period = timedelta(seconds=1)
    worker.wakeup_unblock = False
    worker.shutdown_requested = graceful_shutdown
    worker.task_grace_timeout = None if graceful_shutdown else worker_module.timezone.now()
    worker.cancel_kill_deadline = None
    worker.beat = mock.Mock()
    worker.cancel_abandoned_task = mock.Mock()
    worker.notify_workers = mock.Mock()
    return worker


def _redis_worker(graceful_shutdown):
    worker = object.__new__(redis_worker_module.RedisWorker)
    worker.sentinel = -1
    worker.heartbeat_period = timedelta(seconds=1)
    worker.shutdown_requested = graceful_shutdown
    worker.task_grace_timeout = None if graceful_shutdown else redis_worker_module.timezone.now()
    worker.cancel_kill_deadline = None
    worker.beat = mock.Mock()
    worker._maybe_release_locks = mock.Mock()
    return worker


@pytest.fixture
def in_tmp_dir(tmp_path, monkeypatch):
    # supervise_task creates its TemporaryDirectory in the current directory.
    monkeypatch.chdir(tmp_path)


def _patch_redis_cancel_signal(monkeypatch, pending):
    from pulpcore.tasking import _util, redis_tasks

    monkeypatch.setattr(redis_tasks, "check_cancel_signal", lambda pk: pending["value"])
    monkeypatch.setattr(redis_tasks, "clear_cancel_signal", lambda pk: pending.update(value=False))
    monkeypatch.setattr(_util, "delete_incomplete_resources", mock.Mock())


# --- PulpcoreWorker ------------------------------------------------------------------------


@pytest.mark.parametrize("graceful_shutdown", [True, False], ids=["graceful-shutdown", "running"])
def test_pulpcore_worker_cancel_aborts_task(monkeypatch, in_tmp_dir, graceful_shutdown):
    worker = _pulpcore_worker(graceful_shutdown)
    harness = Harness(
        monkeypatch, worker_module, on_first_select=lambda: setattr(worker, "cancel_task", True)
    )
    task = _make_task()

    worker.supervise_task(task)

    assert harness.kills == [signal.SIGUSR1]
    worker.cancel_abandoned_task.assert_called_once_with(task, TASK_STATES.CANCELED, None)


def test_pulpcore_worker_graceful_shutdown_waits_for_task(monkeypatch, in_tmp_dir):
    worker = _pulpcore_worker(graceful_shutdown=True)
    harness = Harness(monkeypatch, worker_module, finish_after=5)

    worker.supervise_task(_make_task())

    assert harness.kills == []
    assert harness.select_calls == 5
    worker.cancel_abandoned_task.assert_not_called()


# --- RedisWorker ---------------------------------------------------------------------------


@pytest.mark.parametrize("graceful_shutdown", [True, False], ids=["graceful-shutdown", "running"])
def test_redis_worker_cancel_aborts_task(monkeypatch, in_tmp_dir, graceful_shutdown):
    pending = {"value": False}
    _patch_redis_cancel_signal(monkeypatch, pending)
    worker = _redis_worker(graceful_shutdown)
    harness = Harness(
        monkeypatch, redis_worker_module, on_first_select=lambda: pending.update(value=True)
    )
    task = _make_task()

    worker.supervise_task(task)

    assert harness.kills == [signal.SIGUSR1]
    task.set_canceled.assert_called_once_with(final_state=TASK_STATES.CANCELED, reason=None)


def test_redis_worker_graceful_shutdown_waits_for_task(monkeypatch, in_tmp_dir):
    pending = {"value": False}
    _patch_redis_cancel_signal(monkeypatch, pending)
    worker = _redis_worker(graceful_shutdown=True)
    harness = Harness(monkeypatch, redis_worker_module, finish_after=5)
    task = _make_task()

    worker.supervise_task(task)

    assert harness.kills == []
    assert harness.select_calls == 5
    task.set_canceled.assert_not_called()
