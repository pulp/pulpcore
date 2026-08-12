"""
Unit tests for orphan Redis lock cleanup (same-name restart and orphan owners).

Tests use a real Redis provided by the ``redisdb`` pytest fixture (mirroring
``pulp_redisdb`` in test_cache.py) and real DB rows via ``@pytest.mark.django_db``.
"""

from datetime import timedelta

import pytest
import redis
from django.utils import timezone

import pulpcore.app.redis_connection
from pulpcore.app.models import AppStatus, Task
from pulpcore.constants import TASK_STATES
from pulpcore.tasking import redis_locks, redis_worker
from pulpcore.tasking.redis_locks import (
    acquire_locks,
    cleanup_locks_for_owner,
    collect_lock_owners,
    get_owner_registry_key,
    get_task_lock_key,
    resource_to_lock_key,
)
from pulpcore.tasking.redis_worker import RedisWorker


# --------------------------------------------------------------------------- #
# Fixtures / helpers
# --------------------------------------------------------------------------- #
@pytest.fixture
def pulp_redisdb(settings, redisdb, monkeypatch):
    """Point pulpcore's redis connection at the ephemeral ``redisdb`` instance."""
    monkeypatch.setattr(pulpcore.app.redis_connection, "_conn", None)
    monkeypatch.setattr(pulpcore.app.redis_connection, "_a_conn", None)
    settings.CACHE_ENABLED = True
    settings.REDIS_URL = "unix://" + redisdb.get_connection_kwargs()["path"]
    return pulpcore.app.redis_connection.get_redis_connection()


@pytest.fixture
def reset_singleton(monkeypatch):
    """Reset the in-process AppStatus singleton so ``create()`` works per-test."""
    monkeypatch.setattr(AppStatus.objects, "_current_app_status", None)


def _smembers(conn, key):
    """SMEMBERS as a set of str (redisdb returns bytes)."""
    return {m.decode() if isinstance(m, bytes) else m for m in conn.smembers(key)}


def make_app_status(name, online=True, app_type="worker"):
    """Create an AppStatus row directly (bypasses the singleton-enforcing manager)."""
    st = AppStatus(app_type=app_type, name=name, ttl=timedelta(seconds=30))
    st.save()
    if not online:
        AppStatus.objects.filter(pk=st.pk).update(
            last_heartbeat=timezone.now() - timedelta(seconds=3600)
        )
        st.refresh_from_db()
    return st


def make_worker(conn, name, app_status):
    """Build a bare RedisWorker with only the attributes the cleanup methods use."""
    w = RedisWorker.__new__(RedisWorker)
    w.redis_conn = conn
    w.name = name
    w.app_status = app_status
    return w


def seed_locks_via_acquire(conn, owner, task_id, exclusive=None, shared=None):
    """Acquire locks the normal way so the owner registry is populated."""
    exclusive = exclusive or []
    shared = shared or []
    task_lock_key = get_task_lock_key(task_id)
    blocked = acquire_locks(conn, owner, task_lock_key, exclusive, shared)
    assert blocked == []
    return task_lock_key


# --------------------------------------------------------------------------- #
# Registry maintenance in the Lua scripts
# --------------------------------------------------------------------------- #
def test_acquire_registers_owner_locks(pulp_redisdb):
    """Given a worker acquires locks, When acquisition succeeds, Then the owner
    registry set lists every held lock key."""
    conn = pulp_redisdb
    task_lock_key = seed_locks_via_acquire(
        conn, "owner-a", "t1", exclusive=["res-excl"], shared=["res-shared"]
    )

    registry = _smembers(conn, get_owner_registry_key("owner-a"))
    assert task_lock_key in registry
    assert resource_to_lock_key("res-excl") in registry
    assert resource_to_lock_key("res-shared") in registry


def test_release_unregisters_owner_locks(pulp_redisdb):
    """Given locks acquired, When they are released, Then the owner registry set is
    emptied/auto-deleted."""
    conn = pulp_redisdb
    task_lock_key = seed_locks_via_acquire(
        conn, "owner-a", "t1", exclusive=["res-excl"], shared=["res-shared"]
    )
    redis_locks.release_resource_locks(conn, "owner-a", task_lock_key, ["res-excl"], ["res-shared"])
    assert conn.exists(get_owner_registry_key("owner-a")) == 0


# --------------------------------------------------------------------------- #
# cleanup_locks_for_owner / collect_lock_owners
# --------------------------------------------------------------------------- #
def test_cleanup_locks_for_owner_registry_path_only_touches_owner(pulp_redisdb):
    """Given two owners each with registered locks, When one is cleaned,
    Then only that owner's keys are removed and the other is untouched."""
    conn = pulp_redisdb
    seed_locks_via_acquire(conn, "owner-a", "ta", exclusive=["a-excl"], shared=["a-shared"])
    seed_locks_via_acquire(conn, "owner-b", "tb", exclusive=["b-excl"], shared=["b-shared"])

    assert cleanup_locks_for_owner(conn, "owner-a") is True

    assert conn.exists(get_task_lock_key("ta")) == 0
    assert conn.exists(resource_to_lock_key("a-excl")) == 0
    assert conn.exists(resource_to_lock_key("a-shared")) == 0
    assert conn.exists(get_owner_registry_key("owner-a")) == 0
    # owner-b intact
    assert conn.exists(get_task_lock_key("tb")) == 1
    assert conn.exists(resource_to_lock_key("b-excl")) == 1
    assert conn.exists(get_owner_registry_key("owner-b")) == 1


def test_cleanup_locks_for_owner_legacy_scan(pulp_redisdb):
    """Given legacy locks with no registry, When cleaned with the legacy scan
    allowed, Then they are removed (and left alone when the scan is not allowed)."""
    conn = pulp_redisdb
    conn.set(get_task_lock_key("leg"), "legacy-1")
    conn.set(resource_to_lock_key("leg-excl"), "legacy-1")
    conn.sadd(resource_to_lock_key("leg-shared"), "legacy-1")

    # Without legacy scan permission and no registry: no-op.
    assert cleanup_locks_for_owner(conn, "legacy-1", allow_legacy_scan=False) is True
    assert conn.exists(get_task_lock_key("leg")) == 1

    # With legacy scan permission: cleaned.
    assert cleanup_locks_for_owner(conn, "legacy-1", allow_legacy_scan=True) is True
    assert conn.exists(get_task_lock_key("leg")) == 0
    assert conn.exists(resource_to_lock_key("leg-excl")) == 0
    assert conn.exists(resource_to_lock_key("leg-shared")) == 0


def test_cleanup_locks_for_owner_returns_false_on_error():
    """Given Redis raises during cleanup, When cleanup is attempted, Then it
    returns False so the caller can retry later."""

    class BoomConn:
        def exists(self, *args, **kwargs):
            raise redis.RedisError("boom")

    assert cleanup_locks_for_owner(BoomConn(), "owner-x") is False


def test_collect_lock_owners_registry_and_legacy(pulp_redisdb):
    """Registry owners are always collected; legacy owners only when the legacy scan
    is allowed."""
    conn = pulp_redisdb
    seed_locks_via_acquire(conn, "reg-1", "tr", exclusive=["r-excl"])
    conn.set(get_task_lock_key("legt"), "leg-1")

    assert collect_lock_owners(conn, allow_legacy_scan=False) == {"reg-1"}
    assert collect_lock_owners(conn, allow_legacy_scan=True) == {"reg-1", "leg-1"}


# --------------------------------------------------------------------------- #
# release_stale_locks_for_self
# --------------------------------------------------------------------------- #
@pytest.mark.django_db
def test_release_stale_locks_for_self_releases_prior_locks(pulp_redisdb, reset_singleton):
    """Given prior locks under our worker name, When a new incarnation runs
    startup self-cleanup, Then those locks are released."""
    conn = pulp_redisdb
    seed_locks_via_acquire(conn, "1@pod-abc", "old", exclusive=["res"])

    app_status = AppStatus.objects.create(app_type="worker", name="1@pod-abc")
    w = make_worker(conn, "1@pod-abc", app_status)

    assert w.release_stale_locks_for_self() is True
    assert conn.exists(get_task_lock_key("old")) == 0
    assert conn.exists(resource_to_lock_key("res")) == 0


@pytest.mark.django_db
def test_release_stale_locks_for_self_brand_new_skips_scan(
    pulp_redisdb, reset_singleton, monkeypatch
):
    """Given a brand-new worker (no registry, no prior AppStatus), When startup
    self-cleanup runs, Then it does no keyspace SCAN."""
    conn = pulp_redisdb
    app_status = AppStatus.objects.create(app_type="worker", name="brand-new")
    w = make_worker(conn, "brand-new", app_status)

    called = []
    monkeypatch.setattr(conn, "scan_iter", lambda *a, **k: called.append((a, k)) or iter(()))

    assert w.release_stale_locks_for_self() is True
    assert called == []


@pytest.mark.django_db
def test_release_stale_locks_for_self_skips_when_successor_online(pulp_redisdb, reset_singleton):
    """Given another live AppStatus already owns our name, When startup
    self-cleanup runs, Then we skip and leave its locks alone."""
    conn = pulp_redisdb
    seed_locks_via_acquire(conn, "1@pod-abc", "held", exclusive=["res"])

    app_status = AppStatus.objects.create(app_type="worker", name="1@pod-abc")
    make_app_status("1@pod-abc", online=True)  # live successor with same name
    w = make_worker(conn, "1@pod-abc", app_status)

    assert w.release_stale_locks_for_self() is True
    # Locks untouched -- the live peer manages them.
    assert conn.exists(get_task_lock_key("held")) == 1
    assert conn.exists(resource_to_lock_key("res")) == 1


# --------------------------------------------------------------------------- #
# reconcile_orphan_redis_locks
# --------------------------------------------------------------------------- #
@pytest.mark.django_db
def test_reconcile_releases_orphan_owner(pulp_redisdb, reset_singleton):
    """Given locks in Redis with no AppStatus row for the owner, When reconcile
    runs, Then the orphan locks are released."""
    conn = pulp_redisdb
    seed_locks_via_acquire(conn, "orphan-1", "torphan", exclusive=["ores"])

    cleaner = AppStatus.objects.create(app_type="worker", name="cleaner")
    w = make_worker(conn, "cleaner", cleaner)

    w.reconcile_orphan_redis_locks()
    assert conn.exists(get_task_lock_key("torphan")) == 0
    assert conn.exists(resource_to_lock_key("ores")) == 0


@pytest.mark.django_db
def test_reconcile_skips_owner_with_stale_appstatus(pulp_redisdb, reset_singleton):
    """Given an owner with a stale heartbeat but an existing AppStatus row, When
    reconcile runs, Then its locks are NOT released."""
    conn = pulp_redisdb
    seed_locks_via_acquire(conn, "stale-1", "tstale", exclusive=["sres"])
    make_app_status("stale-1", online=False)  # exists but missing heartbeat

    cleaner = AppStatus.objects.create(app_type="worker", name="cleaner")
    w = make_worker(conn, "cleaner", cleaner)

    w.reconcile_orphan_redis_locks()
    assert conn.exists(get_task_lock_key("tstale")) == 1
    assert conn.exists(resource_to_lock_key("sres")) == 1


@pytest.mark.django_db
def test_reconcile_isolates_per_owner_errors(pulp_redisdb, reset_singleton, monkeypatch):
    """Given cleanup of one orphan owner raises, When reconcile runs, Then the
    remaining orphan owners are still processed."""
    conn = pulp_redisdb
    seed_locks_via_acquire(conn, "bad", "tbad", exclusive=["bres"])
    seed_locks_via_acquire(conn, "good", "tgood", exclusive=["gres"])

    cleaner = AppStatus.objects.create(app_type="worker", name="cleaner")
    w = make_worker(conn, "cleaner", cleaner)

    processed = []

    def fake_cleanup(rconn, owner, allow_legacy_scan=False):
        processed.append(owner)
        if owner == "bad":
            raise redis.RedisError("boom")
        return True

    monkeypatch.setattr(redis_worker, "cleanup_locks_for_owner", fake_cleanup)

    w.reconcile_orphan_redis_locks()
    assert "good" in processed  # not aborted by "bad" failing


@pytest.mark.django_db
def test_reconcile_immediate_owner_grace(pulp_redisdb, reset_singleton):
    """Immediate grace: Given an ``immediate-{pk}`` owner whose task is still
    incomplete, When reconcile runs, Then its locks are kept; once the task is
    finished they are reclaimed."""
    conn = pulp_redisdb
    task = Task.objects.create(name="imm", state=TASK_STATES.RUNNING)
    owner = f"immediate-{task.pk}"
    seed_locks_via_acquire(conn, owner, str(task.pk), exclusive=["ires"])

    cleaner = AppStatus.objects.create(app_type="worker", name="cleaner")
    w = make_worker(conn, "cleaner", cleaner)

    # Task still RUNNING -> locks kept.
    w.reconcile_orphan_redis_locks()
    assert conn.exists(resource_to_lock_key("ires")) == 1

    # Task finished -> locks reclaimed.
    Task.objects.filter(pk=task.pk).update(state=TASK_STATES.FAILED)
    w.reconcile_orphan_redis_locks()
    assert conn.exists(resource_to_lock_key("ires")) == 0


# --------------------------------------------------------------------------- #
# cleanup_redis_locks_for_worker
# --------------------------------------------------------------------------- #
@pytest.mark.django_db
def test_cleanup_worker_waiting_task_not_failed(pulp_redisdb, reset_singleton):
    """Given a WAITING task held by a missing worker, When cleanup runs, Then
    its locks are released but the task stays WAITING."""
    conn = pulp_redisdb
    missing = make_app_status("missing-w", online=False)
    task = Task.objects.create(
        name="w", state=TASK_STATES.WAITING, app_lock=missing, reserved_resources_record=["wres"]
    )
    seed_locks_via_acquire(conn, "missing-w", str(task.pk), exclusive=["wres"])

    cleaner = AppStatus.objects.create(app_type="worker", name="cleaner")
    w = make_worker(conn, "cleaner", cleaner)

    assert w.cleanup_redis_locks_for_worker(missing) is True
    task.refresh_from_db()
    assert task.state == TASK_STATES.WAITING
    assert task.app_lock_id is None
    assert conn.exists(resource_to_lock_key("wres")) == 0


@pytest.mark.django_db
def test_cleanup_worker_running_task_failed(pulp_redisdb, reset_singleton):
    """Given a RUNNING task held by a missing worker, When cleanup runs, Then
    its locks are released and the task is FAILED."""
    conn = pulp_redisdb
    missing = make_app_status("missing-w", online=False)
    task = Task.objects.create(
        name="r", state=TASK_STATES.RUNNING, app_lock=missing, reserved_resources_record=["rres"]
    )
    seed_locks_via_acquire(conn, "missing-w", str(task.pk), exclusive=["rres"])

    cleaner = AppStatus.objects.create(app_type="worker", name="cleaner")
    w = make_worker(conn, "cleaner", cleaner)

    assert w.cleanup_redis_locks_for_worker(missing) is True
    task.refresh_from_db()
    assert task.state == TASK_STATES.FAILED
    assert conn.exists(resource_to_lock_key("rres")) == 0


@pytest.mark.django_db
def test_cleanup_worker_returns_false_on_error(pulp_redisdb, reset_singleton, monkeypatch):
    """Given releasing a task's locks raises, When cleanup runs, Then it returns
    False so the AppStatus can be retained for retry."""
    conn = pulp_redisdb
    missing = make_app_status("missing-w", online=False)
    Task.objects.create(
        name="r", state=TASK_STATES.RUNNING, app_lock=missing, reserved_resources_record=["rres"]
    )

    cleaner = AppStatus.objects.create(app_type="worker", name="cleaner")
    w = make_worker(conn, "cleaner", cleaner)

    def boom(*args, **kwargs):
        raise redis.RedisError("boom")

    monkeypatch.setattr(redis_worker, "release_resource_locks", boom)

    assert w.cleanup_redis_locks_for_worker(missing) is False


@pytest.mark.django_db
def test_cleanup_worker_isolates_per_task_errors(pulp_redisdb, reset_singleton, monkeypatch):
    """Given a missing worker with two tasks where releasing the first task's locks
    raises, When cleanup runs, Then the second task is still processed (FAILED, locks
    released) and cleanup returns False.

    The per-task try/except must isolate one Redis failure from the rest.
    """
    conn = pulp_redisdb
    missing = make_app_status("missing-w", online=False)
    bad_task = Task.objects.create(
        name="bad",
        state=TASK_STATES.RUNNING,
        app_lock=missing,
        reserved_resources_record=["bad-res"],
    )
    good_task = Task.objects.create(
        name="good",
        state=TASK_STATES.RUNNING,
        app_lock=missing,
        reserved_resources_record=["good-res"],
    )
    seed_locks_via_acquire(conn, "missing-w", str(bad_task.pk), exclusive=["bad-res"])
    seed_locks_via_acquire(conn, "missing-w", str(good_task.pk), exclusive=["good-res"])

    cleaner = AppStatus.objects.create(app_type="worker", name="cleaner")
    w = make_worker(conn, "cleaner", cleaner)

    real_release = redis_locks.release_resource_locks
    bad_lock_key = get_task_lock_key(bad_task.pk)

    def flaky_release(redis_conn, lock_owner, task_lock_key, *args, **kwargs):
        if task_lock_key == bad_lock_key:
            raise redis.RedisError("boom")
        return real_release(redis_conn, lock_owner, task_lock_key, *args, **kwargs)

    monkeypatch.setattr(redis_worker, "release_resource_locks", flaky_release)

    # The bad task raises, but the good task must still be handled -> overall False.
    assert w.cleanup_redis_locks_for_worker(missing) is False

    good_task.refresh_from_db()
    assert good_task.state == TASK_STATES.FAILED
    assert conn.exists(resource_to_lock_key("good-res")) == 0
    # The bad task never reached its DB update (its release raised first).
    bad_task.refresh_from_db()
    assert bad_task.state == TASK_STATES.RUNNING


@pytest.mark.django_db
def test_cleanup_worker_skips_release_when_successor_online(pulp_redisdb, reset_singleton):
    """Given a missing worker whose name is reused by a live successor, When
    cleanup runs, Then the successor's Redis locks are not released."""
    conn = pulp_redisdb
    missing = make_app_status("reused-name", online=False)
    make_app_status("reused-name", online=True)  # live successor same name
    task = Task.objects.create(
        name="r", state=TASK_STATES.RUNNING, app_lock=missing, reserved_resources_record=["kres"]
    )
    seed_locks_via_acquire(conn, "reused-name", str(task.pk), exclusive=["kres"])

    cleaner = AppStatus.objects.create(app_type="worker", name="cleaner")
    w = make_worker(conn, "cleaner", cleaner)

    w.cleanup_redis_locks_for_worker(missing)
    # Successor's locks left intact.
    assert conn.exists(resource_to_lock_key("kres")) == 1
