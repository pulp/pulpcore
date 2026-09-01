"""
Redis-based worker implementation using distributed lock-based task fetching.

This implementation uses a fundamentally different algorithm where workers compete
directly for task resources using Redis distributed locks, eliminating the need
for the unblocking mechanism.
"""

import functools
import logging
import os
import random
import select
import signal
import time
from datetime import timedelta
from gettext import gettext as _
from multiprocessing import Process
from tempfile import TemporaryDirectory

import redis
from django.conf import settings
from django.db import DatabaseError, IntegrityError, connection, transaction
from django.utils import timezone

from pulpcore.app.apps import pulp_plugin_configs
from pulpcore.app.models import AppStatus, Task
from pulpcore.app.redis_connection import get_redis_connection
from pulpcore.app.util import get_worker_name
from pulpcore.constants import (
    TASK_FINAL_STATES,
    TASK_INCOMPLETE_STATES,
    TASK_METRICS_LOCK,
    TASK_SCHEDULING_LOCK,
    TASK_STATES,
    WORKER_CLEANUP_LOCK,
)
from pulpcore.metrics import init_otel_meter
from pulpcore.tasking._util import (
    dispatch_scheduled_tasks,
    perform_task,
    startup_hook,
)
from pulpcore.tasking.redis_locks import (
    IMMEDIATE_OWNER_PREFIX,
    LEGACY_OWNER_SCAN_INTERVAL,
    LEGACY_OWNER_SCAN_KEY,
    acquire_locks,
    cleanup_locks_for_owner,
    collect_lock_owners,
    extract_task_resources,
    get_owner_registry_key,
    get_task_lock_key,
    release_resource_locks,
    safe_release_task_locks,
)
from pulpcore.tasking.redis_tasks import execute_task
from pulpcore.tasking.storage import WorkerDirectory
from pulpcore.tasking.tasks import using_workdir

_logger = logging.getLogger(__name__)
random.seed()

# Seconds for a task to finish on semi graceful worker shutdown (approx)
TASK_GRACE_INTERVAL = settings.TASK_GRACE_INTERVAL
# Seconds between attempts to kill the subprocess (approx)
TASK_KILL_INTERVAL = 1
# Number of heartbeats between cleaning up worker processes
WORKER_CLEANUP_INTERVAL = 100
# Number of heartbeats between rechecking ignored tasks
IGNORED_TASKS_CLEANUP_INTERVAL = 100
# Number of heartbeats between recording metrics
METRIC_HEARTBEAT_INTERVAL = 3
# Number of tasks to fetch in each query
FETCH_TASK_LIMIT = 20


def exclusive(lock):
    """
    Runs function in a transaction holding the specified lock.
    Returns None if the lock could not be acquired.
    It should be used for actions that only need to be performed by a single worker.
    """

    def _decorator(f):
        @functools.wraps(f)
        def _f(self, *args, **kwargs):
            with transaction.atomic():
                with connection.cursor() as cursor:
                    cursor.execute("SELECT pg_try_advisory_xact_lock(%s, %s)", [0, lock])
                    acquired = cursor.fetchone()[0]
                if acquired:
                    return f(self, *args, **kwargs)
                else:
                    return None

        return _f

    return _decorator


def count_waiting_tasks_for_metric():
    """
    Count WAITING/RUNNING tasks older than five seconds that can run at the same
    time given exclusive/shared resource reservations (FIFO-aware).

    Returns:
        int: Parallelizable unfinished-task count. Callers subtract online workers
            when publishing the OpenTelemetry `waiting_tasks` gauge.
    """
    cutoff_time = timezone.now() - timedelta(seconds=5)

    incomplete_tasks = (
        Task.objects.filter(
            state__in=[TASK_STATES.RUNNING, TASK_STATES.WAITING],
            pulp_created__lt=cutoff_time,
        )
        .order_by("pulp_created")
        .only("reserved_resources_record")
    )

    taken_exclusive = set()
    taken_shared = set()
    parallel_count = 0

    for task in incomplete_tasks:
        exclusive_resources, shared_resources = extract_task_resources(task)
        conflicts = False

        for resource in exclusive_resources:
            if resource in taken_exclusive or resource in taken_shared:
                conflicts = True
                break

        if not conflicts:
            for resource in shared_resources:
                if resource in taken_exclusive:
                    conflicts = True
                    break

        # Always reserve (even on conflict) so FIFO can't be bypassed; see fetch_task.
        # e.g. T1(A,B), T2(B,C), T3(C): without reserving C for T2, T3 counts as +1.
        taken_exclusive.update(exclusive_resources)
        taken_shared.update(shared_resources)
        if conflicts:
            continue

        parallel_count += 1

    return parallel_count


class RedisWorker:
    """
    Worker implementation using Redis distributed lock-based resource acquisition.

    This worker uses a simpler algorithm where:
    1. Query waiting tasks (sorted by creation time, limited)
    2. For each task, try to acquire Redis distributed locks for all resources
    3. If all locks acquired, claim the task
    4. Process resources in deterministic (sorted) order to prevent deadlocks
    5. Lock values contain worker names to enable cleanup of stale locks

    """

    def __init__(self):
        # Notification states from signal handlers
        self.shutdown_requested = False

        self.ignored_task_ids = []
        self.ignored_task_countdown = IGNORED_TASKS_CLEANUP_INTERVAL

        self.task = None
        self.name = get_worker_name()
        self.heartbeat_period = timedelta(seconds=settings.WORKER_TTL / 3)
        self.versions = {app.label: app.version for app in pulp_plugin_configs()}
        self.app_status = AppStatus.objects.create(
            name=self.name, app_type="worker", versions=self.versions
        )

        # This defaults to immediate task cancellation.
        # It will be set into the future on moderately graceful worker shutdown,
        # and set to None for fully graceful shutdown.
        self.task_grace_timeout = timezone.now()

        self.worker_cleanup_countdown = random.randint(
            int(WORKER_CLEANUP_INTERVAL / 10), WORKER_CLEANUP_INTERVAL
        )

        # Metric recording interval
        self.metric_heartbeat_countdown = METRIC_HEARTBEAT_INTERVAL

        # Cache worker count for sleep calculation. Learn the real fleet size at
        # startup so new workers do not poll at the single-worker rate until the
        # first heartbeat (~WORKER_TTL/3). Refreshed on each heartbeat in beat().
        self.num_workers = max(1, AppStatus.objects.online().filter(app_type="worker").count())

        # Redis connection for distributed locks
        self.redis_conn = get_redis_connection()
        if self.redis_conn is None:
            raise RuntimeError(
                f"Redis connection is not available. RedisWorker {self.name} cannot start."
            )
        try:
            self.redis_conn.ping()
        except redis.RedisError:
            raise RuntimeError(f"Redis is not reachable. RedisWorker {self.name} cannot start.")

        # A restarted worker can reuse its name while Redis still holds the dead
        # incarnation's locks. Release them before fetching tasks so we are not
        # blocked by our own stale locks.
        if not self.release_stale_locks_for_self():
            _logger.warning(
                "Startup lock cleanup for %s failed; the worker may be blocked by its "
                "own stale locks until the periodic reconcile runs.",
                self.name,
            )

        # Add a file descriptor to trigger select on signals
        self.sentinel, sentinel_w = os.pipe()
        os.set_blocking(self.sentinel, False)
        os.set_blocking(sentinel_w, False)
        signal.set_wakeup_fd(sentinel_w)

        self._init_instrumentation()

        startup_hook()

        _logger.info(
            "Initialized RedisWorker with Redis lock-based algorithm (online workers=%d)",
            self.num_workers,
        )

    def _init_instrumentation(self):
        """Initialize OpenTelemetry instrumentation if enabled."""
        if settings.OTEL_ENABLED:
            meter = init_otel_meter("pulp-worker")
            self.waiting_tasks_meter = meter.create_gauge(
                name="waiting_tasks",
                description="Number of waiting and running tasks minus the number of workers.",
                unit="tasks",
            )
            self.otel_enabled = True
        else:
            self.otel_enabled = False

    def _signal_handler(self, thesignal, frame):
        """Handle shutdown signals."""
        if thesignal in (signal.SIGHUP, signal.SIGTERM):
            _logger.info(_("Worker %s was requested to shut down gracefully."), self.name)
            # Wait forever...
            self.task_grace_timeout = None
        else:
            # Reset signal handlers to default
            # If you kill the process a second time it's not graceful anymore.
            signal.signal(signal.SIGINT, signal.SIG_DFL)
            signal.signal(signal.SIGTERM, signal.SIG_DFL)
            signal.signal(signal.SIGHUP, signal.SIG_DFL)

            _logger.info(_("Worker %s was requested to shut down."), self.name)
            self.task_grace_timeout = timezone.now() + timezone.timedelta(
                seconds=TASK_GRACE_INTERVAL
            )
        self.shutdown_requested = True

    def shutdown(self):
        """Cleanup worker on shutdown."""
        self.app_status.delete()
        _logger.info(_("Worker %s was shut down."), self.name)

    def handle_worker_heartbeat(self):
        """
        Update worker heartbeat records.

        If the update fails (the record was deleted, the database is unreachable, ...) the worker
        is shut down.
        """
        msg = "Worker heartbeat from '{name}' at time {timestamp}".format(
            timestamp=self.app_status.last_heartbeat, name=self.name
        )
        try:
            self.app_status.save_heartbeat()
            _logger.debug(msg)
        except (IntegrityError, DatabaseError):
            _logger.error(
                "Updating the heartbeat of worker %s failed.",
                self.name,
                exc_info=True,
            )
            self.shutdown_requested = True

    def handle_redis_heartbeat(self):
        """
        Check Redis connection health.

        If the check fails, the worker is shut down, similar to how a PostgreSQL
        heartbeat failure triggers shutdown in handle_worker_heartbeat().
        """
        try:
            self.redis_conn.ping()
        except redis.RedisError:
            _logger.error("Redis connection check failed for worker %s. Shutting down.", self.name)
            self.shutdown_requested = True

    def cleanup_ignored_tasks(self):
        """Remove tasks from ignored list that are no longer incomplete."""
        for pk in (
            Task.objects.filter(pk__in=self.ignored_task_ids)
            .exclude(state__in=TASK_INCOMPLETE_STATES)
            .values_list("pk", flat=True)
        ):
            self.ignored_task_ids.remove(pk)

    def cleanup_redis_locks_for_worker(self, app_worker):
        """
        Clean up Redis locks held by a specific missing worker and fail its tasks.

        For each non-final task held by the missing worker (via app_lock FK):
        1. Release the task's Redis resource locks (unless a live successor reuses
           the name -- then the locks are legitimately held by the successor).
        2. WAITING tasks: release locks but do NOT fail them (crash window between
           acquire_locks() and app_lock assignment).
        3. RUNNING/CANCELING tasks: reassign app_lock to us and mark FAILED.
        Finally, sweep any remaining locks registered under the worker's name.

        Each task is handled in isolation so one failure does not abort the rest.

        Args:
            app_worker (AppStatus): The AppStatus object of the missing worker

        Returns:
            bool: True if cleanup fully succeeded, False if any step failed (so the
                caller can retain the AppStatus row for a later retry pass).
        """
        worker_name = app_worker.name
        success = True

        # If a live successor already reuses this name, its Redis locks are legitimate
        # -- do not release by name. The successor cleared/owns them.
        successor_online = (
            AppStatus.objects.online().filter(name=worker_name).exclude(pk=app_worker.pk).exists()
        )

        tasks = (
            Task.objects.filter(app_lock=app_worker)
            .exclude(state__in=TASK_FINAL_STATES)
            .select_related("pulp_domain")
        )
        for task in tasks:
            try:
                if not successor_online:
                    exclusive_resources, shared_resources = extract_task_resources(task)
                    release_resource_locks(
                        self.redis_conn,
                        worker_name,
                        get_task_lock_key(task.pk),
                        exclusive_resources,
                        shared_resources,
                    )

                if task.state == TASK_STATES.WAITING:
                    # Crash window: locks were acquired but the task never ran.
                    # Release the locks (done above) but leave it WAITING to be
                    # re-fetched; just detach the stale app_lock.
                    Task.objects.filter(pk=task.pk).update(app_lock=None)
                    continue

                # Running/canceling task -> reassign app_lock to us and fail it.
                Task.objects.filter(pk=task.pk).update(app_lock=self.app_status)
                task.app_lock = self.app_status
                task.set_canceling()
                task.set_canceled(final_state=TASK_STATES.FAILED, reason="Worker has gone missing.")
                _logger.warning(
                    "Marked task %s as FAILED (was being executed by missing worker %s)",
                    task.pk,
                    worker_name,
                )
            except Exception as e:
                _logger.error(
                    "Error cleaning up task %s of missing worker %s: %s",
                    task.pk,
                    worker_name,
                    e,
                )
                success = False

        # Registry-driven sweep of any other locks still held under this name.
        if not successor_online:
            if not cleanup_locks_for_owner(self.redis_conn, worker_name, allow_legacy_scan=False):
                success = False

        return success

    def release_stale_locks_for_self(self):
        """
        Release Redis locks lingering under our own worker name at startup.

        A restarted worker can reuse the same name while Redis still holds locks from
        the dead process. Skips if a live successor already owns the name, and skips
        entirely for a brand-new worker (no registry, no prior AppStatus row).

        Returns:
            bool: True if handled (including no-op), False on cleanup error.
        """
        # Another live worker already owns this name -> it manages its own locks.
        if (
            AppStatus.objects.online()
            .filter(name=self.name)
            .exclude(pk=self.app_status.pk)
            .exists()
        ):
            return True

        registry_exists = bool(self.redis_conn.exists(get_owner_registry_key(self.name)))
        prior_status = (
            AppStatus.objects.filter(name=self.name).exclude(pk=self.app_status.pk).exists()
        )

        # Brand-new worker -> nothing could exist under our name; skip any SCAN.
        if not registry_exists and not prior_status:
            return True

        # Rolling upgrade: a prior incarnation left locks but no registry -> allow the
        # legacy SCAN for our own name only.
        allow_legacy = prior_status and not registry_exists
        return cleanup_locks_for_owner(self.redis_conn, self.name, allow_legacy_scan=allow_legacy)

    def _immediate_owner_is_finished(self, owner):
        """Return True if an `immediate-{pk}` owner's task is gone or finished."""
        task_pk = owner[len(IMMEDIATE_OWNER_PREFIX) :]
        return not Task.objects.filter(pk=task_pk, state__in=TASK_INCOMPLETE_STATES).exists()

    def reconcile_orphan_redis_locks(self):
        """
        Release Redis locks whose owner has no AppStatus row at all.

        The missing-worker path only handles owners with a (stale) AppStatus row.
        This reconciles owners whose AppStatus was already deleted (graceful
        shutdown, prior cleanup, kill -9), leaving locks with no DB record.

        Only owners with ZERO AppStatus rows are cleaned; a stale heartbeat still
        counts as "has a row" and is left to the missing-worker path. Each owner is
        handled in isolation. The expensive legacy keyspace SCAN is throttled
        fleet-wide via a Redis key.
        """
        # Winner of the throttle key runs the expensive legacy scan this pass.
        allow_legacy = bool(
            self.redis_conn.set(
                LEGACY_OWNER_SCAN_KEY, self.name, nx=True, ex=LEGACY_OWNER_SCAN_INTERVAL
            )
        )

        owners = collect_lock_owners(self.redis_conn, allow_legacy_scan=allow_legacy)
        if not owners:
            return

        # An owner is orphaned only if it has NO AppStatus row (stale != orphaned).
        existing = set(AppStatus.objects.filter(name__in=owners).values_list("name", flat=True))
        orphans = owners - existing
        if orphans:
            _logger.info("Reconciling Redis locks for %d orphan owner(s).", len(orphans))
        for owner in orphans:
            try:
                if owner.startswith(
                    IMMEDIATE_OWNER_PREFIX
                ) and not self._immediate_owner_is_finished(owner):
                    # Immediate task still running in another process; keep its locks.
                    continue
                cleanup_locks_for_owner(self.redis_conn, owner, allow_legacy_scan=allow_legacy)
            except Exception:
                _logger.exception("Failed reconciling orphan lock owner %s", owner)

    @exclusive(WORKER_CLEANUP_LOCK)
    def app_worker_cleanup(self):
        """Cleanup records of missing app processes and their Redis locks."""
        for app_worker in list(AppStatus.objects.missing()):
            _logger.warning(
                "Cleanup record of missing %s process %s.", app_worker.app_type, app_worker.name
            )
            # Clean up any Redis locks held by this missing process. This includes
            # workers and API processes (which can hold locks for immediate tasks).
            # Only delete the record if cleanup fully succeeded, otherwise retain it
            # for a later retry pass.
            if self.cleanup_redis_locks_for_worker(app_worker):
                app_worker.delete()
            else:
                _logger.warning("Retaining AppStatus %s for a later cleanup pass.", app_worker.name)

        # Reconcile locks whose owner has no AppStatus row at all.
        self.reconcile_orphan_redis_locks()

    @exclusive(TASK_SCHEDULING_LOCK)
    def dispatch_scheduled_tasks(self):
        """Dispatch scheduled tasks."""
        dispatch_scheduled_tasks()

    @exclusive(TASK_METRICS_LOCK)
    def record_waiting_tasks_metric(self):
        """
        Record metrics for waiting tasks in the queue.

        Publishes `count_waiting_tasks_for_metric() - num_workers` as the
        OpenTelemetry `waiting_tasks` gauge.
        """
        self.waiting_tasks_meter.set(count_waiting_tasks_for_metric() - self.num_workers)

    def beat(self):
        """Periodic worker maintenance tasks (heartbeat, cleanup, etc.)."""
        now = timezone.now()
        if self.app_status.last_heartbeat < now - self.heartbeat_period:
            self.handle_worker_heartbeat()
            self.handle_redis_heartbeat()
            if self.ignored_task_ids:
                self.ignored_task_countdown -= 1
                if self.ignored_task_countdown <= 0:
                    self.ignored_task_countdown = IGNORED_TASKS_CLEANUP_INTERVAL
                    self.cleanup_ignored_tasks()

            self.worker_cleanup_countdown -= 1
            if self.worker_cleanup_countdown <= 0:
                self.worker_cleanup_countdown = WORKER_CLEANUP_INTERVAL
                self.app_worker_cleanup()

            self.dispatch_scheduled_tasks()

            # Record metrics periodically
            if self.otel_enabled:
                self.metric_heartbeat_countdown -= 1
                if self.metric_heartbeat_countdown <= 0:
                    self.metric_heartbeat_countdown = METRIC_HEARTBEAT_INTERVAL
                    self.record_waiting_tasks_metric()

            # Update cached worker count for sleep calculation
            self.num_workers = max(1, AppStatus.objects.online().filter(app_type="worker").count())

    def _maybe_release_locks(self, task, mark_released=True):
        """
        Release locks for a task if not already released.

        Args:
            task: Task object to release locks for
            mark_released (bool): Whether to mark locks as released (default: True)

        Returns:
            bool: True if locks were released, False if already released
        """
        if not getattr(task, "_all_locks_released", False):
            exclusive_resources, shared_resources = extract_task_resources(task)
            task_lock_key = get_task_lock_key(task.pk)
            release_resource_locks(
                self.redis_conn,
                self.name,
                task_lock_key,
                exclusive_resources or [],
                shared_resources or [],
            )
            if mark_released:
                task._all_locks_released = True
            return True
        return False

    def is_compatible(self, task):
        """
        Check if this worker is compatible with the task's version requirements.

        Args:
            task: Task object

        Returns:
            bool: True if compatible, False otherwise
        """
        from packaging.version import parse as parse_version

        unmatched_versions = [
            f"task: {label}>={version} worker: {self.versions.get(label)}"
            for label, version in task.versions.items()
            if label not in self.versions
            or parse_version(self.versions[label]) < parse_version(version)
        ]
        if unmatched_versions:
            domain = task.pulp_domain
            _logger.info(
                _("Incompatible versions to execute task %s in domain: %s by worker %s: %s"),
                task.pk,
                domain.name,
                self.name,
                ",".join(unmatched_versions),
            )
            return False
        return True

    def fetch_task(self):
        """
        Fetch an available waiting task using Redis locks.

        Returns:
            Task: A task object if one was successfully locked, None otherwise
        """
        taken_exclusive = set()
        taken_shared = set()

        while True:
            qs = Task.objects.filter(state=TASK_STATES.WAITING, app_lock=None).exclude(
                pk__in=self.ignored_task_ids
            )

            if taken_exclusive or taken_shared:
                blocked = taken_shared | taken_exclusive | {f"shared:{r}" for r in taken_exclusive}
                qs = qs.exclude(reserved_resources_record__overlap=list(blocked))

            waiting_tasks = list(
                qs.order_by("pulp_created").select_related("pulp_domain")[:FETCH_TASK_LIMIT]
            )

            if not waiting_tasks:
                break

            for task in waiting_tasks:
                try:
                    exclusive_resources, shared_resources = extract_task_resources(task)
                    should_skip = False

                    for resource in exclusive_resources:
                        if resource in taken_exclusive or resource in taken_shared:
                            should_skip = True
                            break

                    if not should_skip:
                        for resource in shared_resources:
                            if resource in taken_exclusive:
                                should_skip = True
                                break

                    taken_exclusive.update(exclusive_resources)
                    taken_shared.update(shared_resources)
                    if should_skip:
                        continue

                    task_lock_key = get_task_lock_key(task.pk)
                    blocked_resource_list = acquire_locks(
                        self.redis_conn,
                        self.name,
                        task_lock_key,
                        exclusive_resources,
                        shared_resources,
                    )
                    if blocked_resource_list:
                        continue

                    rows = Task.objects.filter(
                        pk=task.pk, state=TASK_STATES.WAITING, app_lock__isnull=True
                    ).update(app_lock=self.app_status)

                    if rows == 0:
                        safe_release_task_locks(task, lock_owner=self.name)
                        _logger.debug(
                            "WORKER: Task %s no longer claimable, releasing locks", task.pk
                        )
                        continue

                    task.app_lock = self.app_status
                    return task

                except Exception as e:
                    _logger.error("Error processing task %s: %s", task.pk, e)
                    try:
                        safe_release_task_locks(task, lock_owner=self.name)
                    except Exception:
                        pass
                    continue

            if len(waiting_tasks) < FETCH_TASK_LIMIT:
                break

        return None

    def supervise_immediate_task(self, task):
        """Call and supervise the immediate async task process.

        This function must only be called while holding the lock for that task."""
        self.task = task
        _logger.info(
            "WORKER IMMEDIATE EXECUTION: Worker %s executing immediate task %s in domain: %s",
            self.name,
            task.pk,
            task.pulp_domain.name,
        )
        with using_workdir():
            execute_task(task)
        self.task = None

    def supervise_task(self, task):
        """Call and supervise the task process while heart beating.

        This function must only be called while holding the lock for that task.
        Supports task cancellation via Redis signals."""

        from pulpcore.tasking.redis_tasks import check_cancel_signal, clear_cancel_signal

        self.task = task
        cancel_state = None
        cancel_reason = None
        domain = task.pulp_domain
        with TemporaryDirectory(dir=".") as task_working_dir_rel_path:
            task_process = Process(target=perform_task, args=(task.pk, task_working_dir_rel_path))
            task_process.start()

            # Heartbeat while waiting for task to complete
            while task_process.is_alive():
                if cancel_state:
                    if self.task_grace_timeout is None or self.task_grace_timeout > timezone.now():
                        _logger.info("Wait for canceled task to abort.")
                    else:
                        self.task_grace_timeout = timezone.now() + timezone.timedelta(
                            seconds=TASK_KILL_INTERVAL
                        )
                        _logger.info(
                            "Aborting current task %s in domain: %s due to cancellation.",
                            task.pk,
                            domain.name,
                        )
                        os.kill(task_process.pid, signal.SIGUSR1)

                # Wait for a short period or until process completes
                r, w, x = select.select(
                    [self.sentinel, task_process.sentinel],
                    [],
                    [],
                    self.heartbeat_period.seconds,
                )
                # Call beat to keep worker heartbeat alive and perform periodic tasks
                self.beat()

                # Check for cancellation signal
                if check_cancel_signal(task.pk):
                    _logger.info(
                        _("Received signal to cancel current task %s in domain: %s."),
                        task.pk,
                        domain.name,
                    )
                    cancel_state = TASK_STATES.CANCELED
                    clear_cancel_signal(task.pk)

                if self.sentinel in r:
                    os.read(self.sentinel, 256)

                if task_process.sentinel in r:
                    if not task_process.is_alive():
                        break

                # If shutdown was requested, handle gracefully or abort
                if self.shutdown_requested:
                    if self.task_grace_timeout is None or self.task_grace_timeout > timezone.now():
                        msg = (
                            "Worker shutdown requested, waiting for task {pk} in domain: {name} "
                            "to finish.".format(pk=task.pk, name=domain.name)
                        )
                        _logger.info(msg)
                    else:
                        _logger.info(
                            "Aborting current task %s in domain: %s due to worker shutdown.",
                            task.pk,
                            domain.name,
                        )
                        cancel_state = TASK_STATES.FAILED
                        cancel_reason = "Aborted during worker shutdown."

            task_process.join()
            if not cancel_state and task_process.exitcode != 0:
                _logger.warning(
                    "Task process for %s exited with non zero exitcode %i.",
                    task.pk,
                    task_process.exitcode,
                )
                cancel_state = TASK_STATES.FAILED
                if task_process.exitcode < 0:
                    cancel_reason = "Killed by signal {sig_num}.".format(
                        sig_num=-task_process.exitcode
                    )

        # Handle cancellation after task process has finished
        if cancel_state:
            from pulpcore.tasking._util import delete_incomplete_resources

            try:
                # Reload task from database to get current state
                task.refresh_from_db()
                # Only clean up if task is not already in a final state
                # (subprocess may have already handled cancellation)
                if task.state not in TASK_FINAL_STATES:
                    # Release locks BEFORE setting canceled state
                    self._maybe_release_locks(task)
                    task.set_canceling()
                    _logger.info(
                        "Cleaning up task %s in domain: %s and marking as %s.",
                        task.pk,
                        domain.name,
                        cancel_state,
                    )
                    delete_incomplete_resources(task)
                    task.set_canceled(final_state=cancel_state, reason=cancel_reason)
            except Exception:
                _logger.exception("Error in cancel path for task %s", task.pk)
                try:
                    self._maybe_release_locks(task)
                except Exception:
                    _logger.exception("Failed to release locks for task %s", task.pk)

        self.task = None

    def handle_tasks(self):
        """Pick and supervise tasks until there are no more available tasks."""
        while not self.shutdown_requested:
            task = None
            try:
                task = self.fetch_task()
                if task is None:
                    # No task found
                    break

                if not self.is_compatible(task):
                    # Incompatible task, add to ignored list
                    self.ignored_task_ids.append(task.pk)
                    # Atomically release task lock + resource locks so other workers can attempt it
                    self._maybe_release_locks(task, mark_released=False)
                    break

                # Task is compatible, execute it
                if task.immediate:
                    self.supervise_immediate_task(task)
                else:
                    self.supervise_task(task)
            finally:
                # Safety net: if _execute_task() crashed before releasing locks,
                # atomically release all locks here (task lock + resource locks)
                # NOTE: Only for immediate tasks that execute in this process.
                # Deferred tasks execute in subprocess which handles its own lock release.
                if task and task.immediate:
                    self._maybe_release_locks(task)

    def sleep(self):
        """Sleep while calling beat() to maintain heartbeat and perform periodic tasks.

        Sleep time = (num_workers * 10ms) + random_jitter(0.5ms, 1.5ms)
        """
        # Calculate sleep time: (num_workers * 10ms) + jitter(0.5-1.5ms)
        base_sleep_ms = self.num_workers * 10.0
        jitter_ms = random.uniform(0.5, 1.5)
        sleep_time_seconds = (base_sleep_ms + jitter_ms) / 1000.0

        _logger.debug(
            _("Worker %s sleeping for %.4f seconds (workers=%d)"),
            self.name,
            sleep_time_seconds,
            self.num_workers,
        )

        # Call beat before sleeping to maintain heartbeat and perform periodic tasks
        self.beat()

        time.sleep(sleep_time_seconds)

    def run(self, burst=False):
        """Main worker loop."""
        with WorkerDirectory(self.name):
            signal.signal(signal.SIGINT, self._signal_handler)
            signal.signal(signal.SIGTERM, self._signal_handler)
            signal.signal(signal.SIGHUP, self._signal_handler)

            if burst:
                # Burst mode: process tasks until none are available
                self.handle_tasks()
            else:
                # Normal mode: loop and sleep when no tasks available
                while not self.shutdown_requested:
                    if self.shutdown_requested:
                        break
                    self.handle_tasks()
                    if self.shutdown_requested:
                        break
                    # Sleep until work arrives or heartbeat needed
                    self.sleep()

            self.shutdown()
