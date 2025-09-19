from gettext import gettext as _

import functools
import logging
import os
import random
import select
import signal
import socket
from datetime import datetime, timedelta
from multiprocessing import Process
from tempfile import TemporaryDirectory
from packaging.version import parse as parse_version

from django.conf import settings
from django.db import connection, transaction, DatabaseError, IntegrityError
from django.db.models import Case, Count, F, Max, Value, When
from django.utils import timezone

from pulpcore.constants import (
    TASK_STATES,
    TASK_INCOMPLETE_STATES,
    TASK_SCHEDULING_LOCK,
    TASK_UNBLOCKING_LOCK,
    TASK_METRICS_LOCK,
    WORKER_CLEANUP_LOCK,
    TASK_WAKEUP_UNBLOCK,
    TASK_WAKEUP_HANDLE,
)
from pulpcore.metrics import init_otel_meter
from pulpcore.app.apps import pulp_plugin_configs
from pulpcore.app.models import Task, AppStatus

from pulpcore.tasking.storage import WorkerDirectory
from pulpcore.tasking._util import (
    delete_incomplete_resources,
    dispatch_scheduled_tasks,
    perform_task,
    startup_hook,
)

_logger = logging.getLogger(__name__)
random.seed()

# The following four constants are current "best guesses".
# Unless/until we can provide reasonable ways to decide to change their values,
# they will live as constants instead of "proper" settings.

# Seconds for a task to finish on semi graceful worker shutdown (approx)
TASK_GRACE_INTERVAL = settings.TASK_GRACE_INTERVAL
# Seconds between attempts to kill the subprocess (approx)
TASK_KILL_INTERVAL = 1
# Number of heartbeats between cleaning up worker processes (approx)
WORKER_CLEANUP_INTERVAL = 100
# Number of hearbeats between rechecking ignored tasks.
IGNORED_TASKS_CLEANUP_INTERVAL = 100
# Threshold time in seconds of an unblocked task before we consider a queue stalled
THRESHOLD_UNBLOCKED_WAITING_TIME = 5


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


class PulpcoreWorker:
    def __init__(self, auxiliary=False):
        # Notification states from several signal handlers
        self.shutdown_requested = False
        self.wakeup_unblock = False
        self.wakeup_handle = False
        self.cancel_task = False

        self.ignored_task_ids = []
        self.ignored_task_countdown = IGNORED_TASKS_CLEANUP_INTERVAL

        self.auxiliary = auxiliary
        self.task = None
        self.name = f"{os.getpid()}@{socket.getfqdn()}"
        self.heartbeat_period = timedelta(seconds=settings.WORKER_TTL / 3)
        self.last_metric_heartbeat = timezone.now()
        self.versions = {app.label: app.version for app in pulp_plugin_configs()}
        self.cursor = connection.cursor()
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

        # Add a file descriptor to trigger select on signals
        self.sentinel, sentinel_w = os.pipe()
        os.set_blocking(self.sentinel, False)
        os.set_blocking(sentinel_w, False)
        signal.set_wakeup_fd(sentinel_w)

        self._init_instrumentation()

        startup_hook()

    def _init_instrumentation(self):
        if settings.OTEL_ENABLED:
            meter = init_otel_meter("pulp-worker")
            self.tasks_unblocked_queue_meter = meter.create_gauge(
                name="tasks_unblocked_queue",
                description="Number of unblocked tasks waiting in the queue.",
                unit="tasks",
            )
            self.tasks_longest_unblocked_time_meter = meter.create_gauge(
                name="tasks_longest_unblocked_time",
                description="The age of the longest waiting task.",
                unit="seconds",
            )
            self.otel_enabled = True
        else:
            self.otel_enabled = False

    def _signal_handler(self, thesignal, frame):
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

    def _pg_notify_handler(self, notification):
        if notification.channel == "pulp_worker_wakeup":
            if notification.payload == TASK_WAKEUP_UNBLOCK:
                # Auxiliary workers don't do this.
                self.wakeup_unblock = not self.auxiliary
            elif notification.payload == TASK_WAKEUP_HANDLE:
                self.wakeup_handle = True
            else:
                _logger.warning("Unknown wakeup call recieved. Reason: '%s'", notification.payload)
                # We cannot be sure so assume everything happened.
                self.wakeup_unblock = not self.auxiliary
                self.wakeup_handle = True

        elif notification.channel == "pulp_worker_metrics_heartbeat":
            self.last_metric_heartbeat = datetime.fromisoformat(notification.payload)
        elif self.task and notification.channel == "pulp_worker_cancel":
            if notification.payload == str(self.task.pk):
                self.cancel_task = True

    def shutdown(self):
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
            # WARNING: Do not attempt to recycle the connection here.
            # The advisory locks are bound to the connection and we must not loose them.
            _logger.error(f"Updating the heartbeat of worker {self.name} failed.")
            # TODO if shutdown_requested, we may need to be more aggressive.
            self.shutdown_requested = True
            self.cancel_task = True

    def cleanup_ignored_tasks(self):
        for pk in (
            Task.objects.filter(pk__in=self.ignored_task_ids)
            .exclude(state__in=TASK_INCOMPLETE_STATES)
            .values_list("pk", flat=True)
        ):
            self.ignored_task_ids.remove(pk)

    @exclusive(WORKER_CLEANUP_LOCK)
    def app_worker_cleanup(self):
        qs = AppStatus.objects.missing()
        for app_worker in qs:
            _logger.warning(
                "Cleanup record of missing %s process %s.", app_worker.app_type, app_worker.name
            )
        qs.delete()
        # This will also serve as a pacemaker because it will be triggered regularly.
        # Don't bother the others.
        self.wakeup_unblock = True

    @exclusive(TASK_SCHEDULING_LOCK)
    def dispatch_scheduled_tasks(self):
        dispatch_scheduled_tasks()

    @exclusive(TASK_METRICS_LOCK)
    def record_unblocked_waiting_tasks_metric(self, now):
        # This "reporting code" must not me moved inside a task, because it is supposed
        # to be able to report on a congested tasking system to produce reliable results.
        # For performance reasons we aggregate these statistics on a single database call.
        unblocked_tasks_stats = (
            Task.objects.filter(unblocked_at__isnull=False, state=TASK_STATES.WAITING)
            .annotate(unblocked_for=Value(timezone.now()) - F("unblocked_at"))
            .aggregate(
                longest_unblocked_waiting_time=Max("unblocked_for", default=timezone.timedelta(0)),
                unblocked_tasks_count_gte_threshold=Count(
                    Case(
                        When(
                            unblocked_for__gte=Value(
                                timezone.timedelta(seconds=THRESHOLD_UNBLOCKED_WAITING_TIME)
                            ),
                            then=1,
                        )
                    )
                ),
            )
        )

        self.tasks_unblocked_queue_meter.set(
            unblocked_tasks_stats["unblocked_tasks_count_gte_threshold"]
        )
        self.tasks_longest_unblocked_time_meter.set(
            unblocked_tasks_stats["longest_unblocked_waiting_time"].seconds
        )

        self.cursor.execute(f"NOTIFY pulp_worker_metrics_heartbeat, '{str(now)}'")

    def beat(self):
        now = timezone.now()
        if self.app_status.last_heartbeat < now - self.heartbeat_period:
            self.handle_worker_heartbeat()
            if self.ignored_task_ids:
                self.ignored_task_countdown -= 1
                if self.ignored_task_countdown <= 0:
                    self.ignored_task_countdown = IGNORED_TASKS_CLEANUP_INTERVAL
                    self.cleanup_ignored_tasks()
            if not self.auxiliary:
                self.worker_cleanup_countdown -= 1
                if self.worker_cleanup_countdown <= 0:
                    self.worker_cleanup_countdown = WORKER_CLEANUP_INTERVAL
                    self.app_worker_cleanup()

                self.dispatch_scheduled_tasks()

                if self.otel_enabled and now > self.last_metric_heartbeat + self.heartbeat_period:
                    self.record_unblocked_waiting_tasks_metric(now)

    def notify_workers(self, reason):
        self.cursor.execute("SELECT pg_notify('pulp_worker_wakeup', %s)", (reason,))

    def cancel_abandoned_task(self, task, final_state, reason=None):
        """Cancel and clean up an abandoned task.

        This function must only be called while holding the lock for that task. It is a no-op if
        the task is neither in "running" nor "canceling" state.
        """
        # A task is considered abandoned when in running state, but no worker holds its lock
        domain = task.pulp_domain
        task.set_canceling()
        if reason:
            _logger.info(
                "Cleaning up task %s in domain: %s and marking as %s. Reason: %s",
                task.pk,
                domain.name,
                final_state,
                reason,
            )
        else:
            _logger.info(
                _("Cleaning up task %s in domain: %s and marking as %s."),
                task.pk,
                domain.name,
                final_state,
            )
        delete_incomplete_resources(task)
        task.set_canceled(final_state=final_state, reason=reason)
        if task.reserved_resources_record:
            self.notify_workers(TASK_WAKEUP_UNBLOCK)

    def is_compatible(self, task):
        unmatched_versions = [
            f"task: {label}>={version} worker: {self.versions.get(label)}"
            for label, version in task.versions.items()
            if label not in self.versions
            or parse_version(self.versions[label]) < parse_version(version)
        ]
        if unmatched_versions:
            domain = task.pulp_domain  # Hidden db roundtrip
            _logger.info(
                _("Incompatible versions to execute task %s in domain: %s by worker %s: %s"),
                task.pk,
                domain.name,
                self.name,
                ",".join(unmatched_versions),
            )
            return False
        return True

    def unblock_tasks(self):
        """Iterate over waiting tasks and mark them unblocked accordingly.

        This function also handles the communication around it.
        In order to prevent multiple workers to attempt unblocking tasks at the same time it tries
        to acquire a lock and just returns on failure to do so.
        Also it clears the notification about tasks to be unblocked and sends the notification that
        new unblocked tasks are made available.

        Returns None if another worker held the lock, True if unblocked tasks exist, else False.
        """

        assert not self.auxiliary

        self.wakeup_unblock = False
        result = self._unblock_tasks()
        if result is not None and (
            Task.objects.filter(
                state__in=[TASK_STATES.WAITING, TASK_STATES.CANCELING], app_lock=None
            )
            .exclude(unblocked_at=None)
            .exists()
        ):
            self.notify_workers(TASK_WAKEUP_HANDLE)
            return True

        return result

    @exclusive(TASK_UNBLOCKING_LOCK)
    def _unblock_tasks(self):
        """Iterate over waiting tasks and mark them unblocked accordingly."""

        taken_exclusive_resources = set()
        taken_shared_resources = set()
        # When batching this query, be sure to use "pulp_created" as a cursor
        for task in (
            Task.objects.filter(state__in=TASK_INCOMPLETE_STATES)
            .order_by("pulp_created")
            .select_related("pulp_domain")
        ):
            reserved_resources_record = task.reserved_resources_record or []
            exclusive_resources = [
                resource
                for resource in reserved_resources_record
                if not resource.startswith("shared:")
            ]
            shared_resources = [
                resource[7:]
                for resource in reserved_resources_record
                if resource.startswith("shared:") and resource[7:] not in exclusive_resources
            ]
            if task.state == TASK_STATES.CANCELING:
                if task.unblocked_at is None:
                    _logger.debug(
                        "Marking canceling task %s in domain: %s unblocked.",
                        task.pk,
                        task.pulp_domain.name,
                    )
                    task.unblock()

            elif (
                task.state == TASK_STATES.WAITING
                and task.unblocked_at is None
                # No exclusive resource taken?
                and not any(
                    resource in taken_exclusive_resources or resource in taken_shared_resources
                    for resource in exclusive_resources
                )
                # No shared resource exclusively taken?
                and not any(resource in taken_exclusive_resources for resource in shared_resources)
            ):
                _logger.debug(
                    "Marking waiting task %s in domain: %s unblocked.",
                    task.pk,
                    task.pulp_domain.name,
                )
                task.unblock()
            elif task.state == TASK_STATES.RUNNING and task.unblocked_at is None:
                # This should not happen in normal operation.
                # And it is only an issue if the worker running that task died, because it will
                # never be considered for cleanup.
                # But during at least one specific upgrade this situation can emerge.
                # In this case, we can assume that the old algorithm was employed to identify the
                # task as unblocked, and we just rectify the situation here.
                _logger.warning(
                    "Running task %s was not previously marked unblocked. Fixing.", task.pk
                )
                task.unblock()

            # Record the resources of the pending task
            taken_exclusive_resources.update(exclusive_resources)
            taken_shared_resources.update(shared_resources)
        return False

    def sleep(self):
        """Wait for signals on the wakeup channel while heart beating."""

        _logger.debug(_("Worker %s entering sleep state."), self.name)
        while not self.shutdown_requested and not self.wakeup_handle:
            r, w, x = select.select(
                [self.sentinel, connection.connection],
                [],
                [],
                0 if self.wakeup_unblock else self.heartbeat_period.seconds,
            )
            self.beat()
            if connection.connection in r:
                connection.connection.execute("SELECT 1")
            if self.wakeup_unblock:
                self.unblock_tasks()
            if self.sentinel in r:
                os.read(self.sentinel, 256)
        _logger.debug(_("Worker %s leaving sleep state."), self.name)

    def supervise_task(self, task):
        """Call and supervise the task process while heart beating.

        This function must only be called while holding the lock for that task."""

        self.cancel_task = False
        self.task = task
        cancel_state = None
        cancel_reason = None
        domain = task.pulp_domain
        with TemporaryDirectory(dir=".") as task_working_dir_rel_path:
            task_process = Process(target=perform_task, args=(task.pk, task_working_dir_rel_path))
            task_process.start()
            while True:
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

                r, w, x = select.select(
                    [self.sentinel, connection.connection, task_process.sentinel],
                    [],
                    [],
                    0 if self.wakeup_unblock or self.cancel_task else self.heartbeat_period.seconds,
                )
                self.beat()
                if connection.connection in r:
                    connection.connection.execute("SELECT 1")
                if self.cancel_task:
                    _logger.info(
                        _("Received signal to cancel current task %s in domain: %s."),
                        task.pk,
                        domain.name,
                    )
                    cancel_state = TASK_STATES.CANCELED
                    self.cancel_task = False
                if self.wakeup_unblock:
                    self.unblock_tasks()
                if task_process.sentinel in r:
                    if not task_process.is_alive():
                        break
                if self.sentinel in r:
                    os.read(self.sentinel, 256)
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
                else:
                    cancel_reason = "Task process died unexpectedly with exitcode {code}.".format(
                        code=task_process.exitcode
                    )
            if cancel_state:
                self.cancel_abandoned_task(task, cancel_state, cancel_reason)
        if task.reserved_resources_record:
            self.notify_workers(TASK_WAKEUP_UNBLOCK)
        self.task = None

    def fetch_task(self):
        """
        Fetch an available unblocked task and set the app_lock to this process.
        """
        # The PostgreSQL returning logic cannot be represented in Django ORM.
        # Also I doubt that rewriting this in ORM makes it any more readable.
        query = """
            UPDATE core_task
            SET app_lock_id = %s
            WHERE pulp_id IN (
                SELECT pulp_id FROM core_task
                WHERE
                    state = ANY(%s)
                    AND unblocked_at IS NOT NULL
                    AND app_lock_id IS NULL
                    AND NOT pulp_id = ANY(%s)
                ORDER BY immediate DESC, pulp_created + '8 s'::interval * random()
                LIMIT 1
                FOR UPDATE SKIP LOCKED
            )
            RETURNING
                pulp_id,
                state,
                unblocked_at,
                versions,
                pulp_domain_id,
                reserved_resources_record
        """
        qs = Task.objects.raw(
            query,
            [
                self.app_status.pulp_id,
                list(TASK_INCOMPLETE_STATES),
                self.ignored_task_ids,
            ],
        )
        return next(iter(qs), None)

    def handle_unblocked_tasks(self):
        """Pick and supervise tasks until there are no more available tasks.

        Failing to detect new available tasks can lead to a stuck state, as the workers
        would go to sleep and wouldn't be able to know about the unhandled task until
        an external wakeup event occurs (e.g., new worker startup or new task gets in).
        """
        while not self.shutdown_requested:
            # Clear pending wakeups. We are about to handle them anyway.
            self.wakeup_handle = False

            task = self.fetch_task()
            if task is None:
                # No task found
                break
            try:
                if task.state == TASK_STATES.CANCELING:
                    # No worker picked this task up before being canceled.
                    # Or the worker disappeared before handling the canceling.
                    self.cancel_abandoned_task(task, TASK_STATES.CANCELED)
                elif task.state == TASK_STATES.RUNNING:
                    # A running task without a lock must be abandoned.
                    self.cancel_abandoned_task(task, TASK_STATES.FAILED, "Worker has gone missing.")
                elif task.state == TASK_STATES.WAITING and self.is_compatible(task):
                    self.supervise_task(task)
                else:
                    # Probably incompatible, but for whatever reason we didn't pick it up this time,
                    # we don't need to look at it ever again.
                    self.ignored_task_ids.append(task.pk)
            finally:
                rows = Task.objects.filter(pk=task.pk, app_lock=AppStatus.objects.current()).update(
                    app_lock=None
                )
                if rows != 1:
                    raise RuntimeError("Something other than us is messing around with locks.")

    def run(self, burst=False):
        with WorkerDirectory(self.name):
            signal.signal(signal.SIGINT, self._signal_handler)
            signal.signal(signal.SIGTERM, self._signal_handler)
            signal.signal(signal.SIGHUP, self._signal_handler)
            # Subscribe to pgsql channels
            connection.connection.add_notify_handler(self._pg_notify_handler)
            self.cursor.execute("LISTEN pulp_worker_cancel")
            self.cursor.execute("LISTEN pulp_worker_metrics_heartbeat")
            if burst:
                if not self.auxiliary:
                    # Attempt to flush the task queue completely.
                    # Stop iteration if no new tasks were found to unblock.
                    while self.unblock_tasks() is not False:
                        self.handle_unblocked_tasks()
                self.handle_unblocked_tasks()
            else:
                self.cursor.execute("LISTEN pulp_worker_wakeup")
                while not self.shutdown_requested:
                    # do work
                    if self.shutdown_requested:
                        break
                    self.handle_unblocked_tasks()
                    if self.shutdown_requested:
                        break
                    # rest until notified to wakeup
                    self.sleep()
                self.cursor.execute("UNLISTEN pulp_worker_wakeup")
            self.cursor.execute("UNLISTEN pulp_worker_metrics_heartbeat")
            self.cursor.execute("UNLISTEN pulp_worker_cancel")
            self.shutdown()
