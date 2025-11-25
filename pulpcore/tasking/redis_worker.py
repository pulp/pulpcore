"""
Redis-based worker implementation using distributed lock-based task fetching.

This implementation uses a fundamentally different algorithm where workers compete
directly for task resources using Redis distributed locks, eliminating the need
for the unblocking mechanism and all task cancellation support.
"""

from gettext import gettext as _
import functools
import logging
import os
import random
import select
import signal
import time
from datetime import timedelta
from multiprocessing import Process
from tempfile import TemporaryDirectory

from django.conf import settings
from django.db import connection, transaction, DatabaseError, IntegrityError
from django.utils import timezone

from pulpcore.constants import (
    TASK_STATES,
    TASK_INCOMPLETE_STATES,
    TASK_FINAL_STATES,
    TASK_SCHEDULING_LOCK,
    WORKER_CLEANUP_LOCK,
    TASK_METRICS_LOCK,
)
from pulpcore.metrics import init_otel_meter
from pulpcore.app.apps import pulp_plugin_configs
from pulpcore.app.util import get_worker_name
from pulpcore.app.models import Task, AppStatus
from pulpcore.app.redis_connection import get_redis_connection
from pulpcore.tasking.storage import WorkerDirectory
from pulpcore.tasking._util import (
    dispatch_scheduled_tasks,
    perform_task,
    startup_hook,
)
from pulpcore.tasking.redis_locks import (
    release_resource_locks,
    acquire_locks,
    extract_task_resources,
    get_task_lock_key,
)
from pulpcore.tasking.tasks import using_workdir
from pulpcore.tasking.redis_tasks import execute_task


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


class RedisWorker:
    """
    Worker implementation using Redis distributed lock-based resource acquisition.

    This worker uses a simpler algorithm where:
    1. Query waiting tasks (sorted by creation time, limited)
    2. For each task, try to acquire Redis distributed locks for all resources
    3. If all locks acquired, claim the task
    4. Process resources in deterministic (sorted) order to prevent deadlocks
    5. Lock values contain worker names to enable cleanup of stale locks

    Note: This implementation does NOT support task cancellation.
    """

    def __init__(self):
        # Notification states from signal handlers
        self.shutdown_requested = False
        self.wakeup_handle = False

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

        # Cache worker count for sleep calculation (updated during beat)
        self.num_workers = 1

        # Redis connection for distributed locks
        self.redis_conn = get_redis_connection()

        # Add a file descriptor to trigger select on signals
        self.sentinel, sentinel_w = os.pipe()
        os.set_blocking(self.sentinel, False)
        os.set_blocking(sentinel_w, False)
        signal.set_wakeup_fd(sentinel_w)

        self._init_instrumentation()

        startup_hook()

        _logger.info("Initialized RedisWorker with Redis lock-based algorithm")

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
            _logger.error(f"Updating the heartbeat of worker {self.name} failed.")
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
        Clean up Redis locks held by a specific worker and fail its tasks.

        This is called when a worker is detected as missing to:
        1. Query the database for tasks held by the worker (via app_lock FK)
        2. Release the task's Redis resource locks
        3. Set app_lock to the current (cleaning) worker
        4. Mark those tasks as FAILED

        If the database query finds no tasks, falls back to scanning Redis
        to catch the edge case where a worker crashed between fetch_task()
        (Redis locks acquired) and set_running() (which sets app_lock).
        In that case the task is still WAITING, so we only release the Redis
        locks and let another worker pick it up.

        Args:
            app_worker (AppStatus): The AppStatus object of the missing worker
        """
        if not self.redis_conn:
            return

        worker_name = app_worker.name

        try:
            # Primary path: query database for the task held by the missing worker.
            # A worker runs at most one task at a time, so we expect at most one.
            task = (
                Task.objects.filter(app_lock=app_worker)
                .exclude(state__in=TASK_FINAL_STATES)
                .select_related("pulp_domain")
                .first()
            )

            if task:
                # Extract resources from the task's reserved_resources_record
                exclusive_resources, shared_resources = extract_task_resources(task)

                # Release Redis locks using the missing worker's name as the lock owner
                task_lock_key = get_task_lock_key(task.pk)
                release_resource_locks(
                    self.redis_conn,
                    worker_name,
                    task_lock_key,
                    exclusive_resources,
                    shared_resources,
                )
                _logger.info(
                    "Released task lock + %d exclusive + %d shared resource locks "
                    "for task %s from missing worker %s",
                    len(exclusive_resources),
                    len(shared_resources),
                    task.pk,
                    worker_name,
                )

                # Set app_lock to the current (cleaning) worker so set_failed()
                # ownership check passes
                Task.objects.filter(pk=task.pk).update(app_lock=self.app_status)
                task.app_lock = self.app_status

                # Set to canceling first
                task.set_canceling()
                error_msg = "Worker has gone missing."
                task.set_canceled(final_state=TASK_STATES.FAILED, reason=error_msg)
                _logger.warning(
                    "Marked task %s as FAILED " "(was being executed by missing worker %s)",
                    task.pk,
                    worker_name,
                )
            else:
                # Fallback: scan Redis for an orphaned lock if no task found in DB.
                # This catches the edge case where a worker crashed between
                # fetch_task() (Redis locks acquired) and set_running() (sets
                # app_lock). In this window the task is still WAITING with no
                # app_lock, so we just release the Redis locks and let another
                # worker pick it up.
                task_lock_pattern = "task:*"
                for key in self.redis_conn.scan_iter(match=task_lock_pattern, count=100):
                    lock_holder = self.redis_conn.get(key)
                    if lock_holder and lock_holder.decode("utf-8") == worker_name:
                        task_uuid = key.decode("utf-8").split(":", 1)[1]

                        try:
                            task = Task.objects.select_related("pulp_domain").get(pk=task_uuid)

                            # Extract resources and release Redis locks
                            exclusive_resources, shared_resources = extract_task_resources(task)
                            task_lock_key = get_task_lock_key(task_uuid)
                            release_resource_locks(
                                self.redis_conn,
                                worker_name,
                                task_lock_key,
                                exclusive_resources,
                                shared_resources,
                            )
                            _logger.info(
                                "Fallback: released Redis locks for task %s "
                                "from missing worker %s (task remains %s)",
                                task_uuid,
                                worker_name,
                                task.state,
                            )
                        except Task.DoesNotExist:
                            _logger.warning(
                                "Task %s locked by missing worker %s " "not found in database",
                                task_uuid,
                                worker_name,
                            )
                            # Delete the orphaned Redis task lock
                            self.redis_conn.delete(key)
        except Exception as e:
            _logger.error("Error cleaning up locks for worker %s: %s", worker_name, e)

    @exclusive(WORKER_CLEANUP_LOCK)
    def app_worker_cleanup(self):
        """Cleanup records of missing app processes and their Redis locks."""
        qs = AppStatus.objects.missing()
        for app_worker in qs:
            _logger.warning(
                "Cleanup record of missing %s process %s.", app_worker.app_type, app_worker.name
            )
            # Clean up any Redis locks held by this missing process
            # This includes workers and API processes (which can hold locks for immediate tasks)
            self.cleanup_redis_locks_for_worker(app_worker)
        qs.delete()

    @exclusive(TASK_SCHEDULING_LOCK)
    def dispatch_scheduled_tasks(self):
        """Dispatch scheduled tasks."""
        dispatch_scheduled_tasks()

    @exclusive(TASK_METRICS_LOCK)
    def record_waiting_tasks_metric(self):
        """
        Record metrics for waiting tasks in the queue.

        This method counts all tasks in RUNNING or WAITING state that are older
        than 5 seconds, then subtracts the number of active workers to get the
        number of tasks waiting to be picked up by workers.
        """
        # Calculate the cutoff time (5 seconds ago)
        cutoff_time = timezone.now() - timedelta(seconds=5)

        # Count tasks in RUNNING or WAITING state older than 5 seconds
        task_count = Task.objects.filter(
            state__in=[TASK_STATES.RUNNING, TASK_STATES.WAITING], pulp_created__lt=cutoff_time
        ).count()

        # Calculate waiting tasks: total tasks - workers
        waiting_tasks = task_count - self.num_workers

        # Set the metric value
        self.waiting_tasks_meter.set(waiting_tasks)

        _logger.debug(
            "Waiting tasks metric: %d tasks (%d total tasks older than 5s - %d workers)",
            waiting_tasks,
            task_count,
            self.num_workers,
        )

    def beat(self):
        """Periodic worker maintenance tasks (heartbeat, cleanup, etc.)."""
        now = timezone.now()
        if self.app_status.last_heartbeat < now - self.heartbeat_period:
            self.handle_worker_heartbeat()
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
            self.num_workers = AppStatus.objects.online().filter(app_type="worker").count()

    def _release_resource_locks(self, task_lock_key, resources, shared_resources=None):
        """
        Atomically release task lock and resource locks.

        Uses a Lua script to ensure we only release locks that we own.

        Args:
            task_lock_key (str): Redis key for the task lock (e.g., "task:{task_id}")
            resources (list): List of exclusive resource names to release locks for
            shared_resources (list): Optional list of shared resource names
        """
        release_resource_locks(
            self.redis_conn, self.name, task_lock_key, resources, shared_resources
        )

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
            self._release_resource_locks(
                task_lock_key, exclusive_resources or [], shared_resources or []
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

        This method:
        1. Queries waiting tasks (sorted by creation time, limited)
        2. For each task, attempts to acquire Redis distributed locks for exclusive resources
        3. If resource locks acquired, attempts to claim the task
           with a Redis task lock (24h expiration)
        4. Returns the first task for which both locks can be acquired

        Returns:
            Task: A task object if one was successfully locked, None otherwise
        """
        # Query waiting tasks, sorted by creation time, limited
        waiting_tasks = (
            Task.objects.filter(state=TASK_STATES.WAITING)
            .exclude(pk__in=self.ignored_task_ids)
            .order_by("pulp_created")
            .select_related("pulp_domain")[:FETCH_TASK_LIMIT]
        )

        # Track resources that are blocked to preserve FIFO ordering
        # blocked_exclusive: resources where an earlier task wanted exclusive access and failed
        # blocked_shared: resources where an earlier task wanted shared access and failed
        blocked_exclusive = set()
        blocked_shared = set()

        # Try to acquire locks for each task
        for task in waiting_tasks:
            try:
                # Extract resources from task
                exclusive_resources, shared_resources = extract_task_resources(task)

                # Check if this task should skip to preserve FIFO ordering
                should_skip = False

                # Skip if we need exclusive access but an earlier task already tried and failed
                for resource in exclusive_resources:
                    if resource in blocked_exclusive or resource in blocked_shared:
                        should_skip = True
                        break

                # Skip if we need shared access but earlier task wanted it and exclusive lock exists
                if not should_skip:
                    for resource in shared_resources:
                        if resource in blocked_shared:
                            should_skip = True
                            break

                if should_skip:
                    continue

                # Atomically try to acquire task lock and resource locks in a single operation
                task_lock_key = get_task_lock_key(task.pk)

                blocked_resource_list = acquire_locks(
                    self.redis_conn, self.name, task_lock_key, exclusive_resources, shared_resources
                )

                if not blocked_resource_list:
                    # All locks acquired successfully (task lock + resource locks)!
                    return task
                else:
                    # Failed to acquire locks (task lock or resource locks blocked)
                    # No cleanup needed - Lua script is all-or-nothing
                    if "__task_lock__" not in blocked_resource_list:
                        # Mark resources as blocked for FIFO ordering
                        # If this task wanted exclusive access,
                        # block exclusive access for later tasks
                        for resource in exclusive_resources:
                            if resource in blocked_resource_list:
                                blocked_exclusive.add(resource)
                        # If this task wanted shared access, block shared access for later tasks
                        # (only if exclusive lock exists, which is why it failed)
                        for resource in shared_resources:
                            if resource in blocked_resource_list:
                                blocked_shared.add(resource)
                    continue

            except Exception as e:
                _logger.error("Error processing task %s: %s", task.pk, e)
                continue

        # No task could be locked
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
        _logger.info(
            "WORKER DEFERRED EXECUTION: Worker %s executing deferred task %s in domain: %s",
            self.name,
            task.pk,
            domain.name,
        )
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

            # Reload task from database to get current state
            task.refresh_from_db()
            # Only clean up if task is not already in a final state
            # (subprocess may have already handled cancellation)
            if task.state not in TASK_FINAL_STATES:
                # Release locks BEFORE setting canceled state
                # Atomically release task lock + resource locks in a single operation
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

                # Check if task is still WAITING after acquiring locks
                # (an API process might have executed it between query and lock acquisition)
                task.refresh_from_db()
                if task.state != TASK_STATES.WAITING:
                    # Task was already executed, release locks and skip
                    _logger.info(
                        "Task %s already in state '%s' after acquiring locks, skipping execution",
                        task.pk,
                        task.state,
                    )
                    self._maybe_release_locks(task)
                    continue

                # Task is compatible and still waiting, execute it
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
