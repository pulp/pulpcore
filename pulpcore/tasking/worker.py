from gettext import gettext as _

import logging
import os
import random
import select
import signal
import socket
import contextlib
from datetime import datetime, timedelta
from multiprocessing import Process
from tempfile import TemporaryDirectory
from packaging.version import parse as parse_version
from opentelemetry.metrics import get_meter

from django.conf import settings
from django.db import connection
from django.db.models import Case, Count, F, Max, Value, When
from django.utils import timezone

from pulpcore.constants import (
    TASK_STATES,
    TASK_INCOMPLETE_STATES,
    TASK_SCHEDULING_LOCK,
    TASK_UNBLOCKING_LOCK,
    TASK_METRICS_HEARTBEAT_LOCK,
)
from pulpcore.app.apps import pulp_plugin_configs
from pulpcore.app.models import Worker, Task, ApiAppStatus, ContentAppStatus
from pulpcore.app.util import PGAdvisoryLock
from pulpcore.exceptions import AdvisoryLockError

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

# Number of heartbeats for a task to finish on graceful worker shutdown (approx)
TASK_GRACE_INTERVAL = 3
# Number of heartbeats between attempts to kill the subprocess (approx)
TASK_KILL_INTERVAL = 1
# Number of heartbeats between cleaning up worker processes (approx)
WORKER_CLEANUP_INTERVAL = 100
# Threshold time in seconds of an unblocked task before we consider a queue stalled
THRESHOLD_UNBLOCKED_WAITING_TIME = 5


class PulpcoreWorker:
    def __init__(self):
        # Notification states from several signal handlers
        self.shutdown_requested = False
        self.wakeup = False
        self.cancel_task = False

        self.task = None
        self.name = f"{os.getpid()}@{socket.getfqdn()}"
        self.heartbeat_period = timedelta(seconds=settings.WORKER_TTL / 3)
        self.last_metric_heartbeat = timezone.now()
        self.versions = {app.label: app.version for app in pulp_plugin_configs()}
        self.cursor = connection.cursor()
        self.worker = self.handle_worker_heartbeat()
        self.task_grace_timeout = 0
        self.worker_cleanup_countdown = random.randint(
            WORKER_CLEANUP_INTERVAL / 10, WORKER_CLEANUP_INTERVAL
        )

        meter = get_meter(__name__)
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

        # Add a file descriptor to trigger select on signals
        self.sentinel, sentinel_w = os.pipe()
        os.set_blocking(self.sentinel, False)
        os.set_blocking(sentinel_w, False)
        signal.set_wakeup_fd(sentinel_w)

        startup_hook()

    def _signal_handler(self, thesignal, frame):
        if thesignal in (signal.SIGHUP, signal.SIGTERM):
            _logger.info(_("Worker %s was requested to shut down gracefully."), self.name)
            self.task_grace_timeout = -1
        else:
            # Reset signal handlers to default
            # If you kill the process a second time it's not graceful anymore.
            signal.signal(signal.SIGINT, signal.SIG_DFL)
            signal.signal(signal.SIGTERM, signal.SIG_DFL)
            signal.signal(signal.SIGHUP, signal.SIG_DFL)

            _logger.info(_("Worker %s was requested to shut down."), self.name)
            self.task_grace_timeout = TASK_GRACE_INTERVAL
        self.shutdown_requested = True

    def _pg_notify_handler(self, notification):
        if notification.channel == "pulp_worker_wakeup":
            self.wakeup = True
        elif notification.channel == "pulp_worker_metrics_heartbeat":
            self.last_metric_heartbeat = datetime.fromisoformat(notification.payload)
        elif self.task and notification.channel == "pulp_worker_cancel":
            if notification.payload == str(self.task.pk):
                self.cancel_task = True

    def handle_worker_heartbeat(self):
        """
        Create or update worker heartbeat records.

        Existing Worker objects are searched for one to update. If an existing one is found, it is
        updated. Otherwise a new Worker entry is created. Logging at the info level is also done.

        """
        worker, created = Worker.objects.get_or_create(
            name=self.name, defaults={"versions": self.versions}
        )
        if not created and worker.versions != self.versions:
            worker.versions = self.versions
            worker.save(update_fields=["versions"])

        if created:
            _logger.info(_("New worker '{name}' discovered").format(name=self.name))
        elif worker.online is False:
            _logger.info(_("Worker '{name}' is back online.").format(name=self.name))

        worker.save_heartbeat()

        msg = "Worker heartbeat from '{name}' at time {timestamp}".format(
            timestamp=worker.last_heartbeat, name=self.name
        )
        _logger.debug(msg)

        return worker

    def shutdown(self):
        self.worker.delete()
        _logger.info(_("Worker %s was shut down."), self.name)

    def worker_cleanup(self):
        for cls, cls_name in (
            (Worker, "pulp"),
            (ApiAppStatus, "api"),
            (ContentAppStatus, "content"),
        ):
            qs = cls.objects.missing(age=timedelta(days=7))
            if qs:
                for app_worker in qs:
                    _logger.info(_("Clean missing %s worker %s."), cls_name, app_worker.name)
                qs.delete()

    def beat(self):
        if self.worker.last_heartbeat < timezone.now() - self.heartbeat_period:
            self.worker = self.handle_worker_heartbeat()
            if self.task_grace_timeout > 0:
                self.task_grace_timeout -= 1
            self.worker_cleanup_countdown -= 1
            if self.worker_cleanup_countdown <= 0:
                self.worker_cleanup_countdown = WORKER_CLEANUP_INTERVAL
                self.worker_cleanup()
            with contextlib.suppress(AdvisoryLockError), PGAdvisoryLock(TASK_SCHEDULING_LOCK):
                dispatch_scheduled_tasks()
            self.record_unblocked_waiting_tasks_metric()

    def notify_workers(self):
        self.cursor.execute("NOTIFY pulp_worker_wakeup")

    def cancel_abandoned_task(self, task, final_state, reason=None):
        """Cancel and clean up an abandoned task.

        This function must only be called while holding the lock for that task. It is a no-op if
        the task is neither in "running" nor "canceling" state.

        Return ``True`` if the task was actually canceled, ``False`` otherwise.
        """
        # A task is considered abandoned when in running state, but no worker holds its lock
        try:
            task.set_canceling()
        except RuntimeError:
            return False
        if reason:
            _logger.info(
                "Cleaning up task %s and marking as %s. Reason: %s",
                task.pk,
                final_state,
                reason,
            )
        else:
            _logger.info(_("Cleaning up task %s and marking as %s."), task.pk, final_state)
        delete_incomplete_resources(task)
        task.set_canceled(final_state=final_state, reason=reason)
        if task.reserved_resources_record:
            self.notify_workers()
        return True

    def is_compatible(self, task):
        unmatched_versions = [
            f"task: {label}>={version} worker: {self.versions.get(label)}"
            for label, version in task.versions.items()
            if label not in self.versions
            or parse_version(self.versions[label]) < parse_version(version)
        ]
        if unmatched_versions:
            _logger.info(
                _("Incompatible versions to execute task %s by worker %s: %s"),
                task.pk,
                self.name,
                ",".join(unmatched_versions),
            )
            return False
        return True

    def identify_unblocked_tasks(self):
        """Iterate over waiting tasks and mark them unblocked accordingly."""

        changed = False
        taken_exclusive_resources = set()
        taken_shared_resources = set()
        # When batching this query, be sure to use "pulp_created" as a cursor
        for task in Task.objects.filter(state__in=TASK_INCOMPLETE_STATES).order_by("pulp_created"):
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
                    _logger.debug("Marking canceling task %s unblocked.", task.pk)
                    task.unblock()
                    changed = True
                # Don't consider this task's resources as held.
                continue

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
                _logger.debug("Marking waiting task %s unblocked.", task.pk)
                task.unblock()
                changed = True

            # Record the resources of the pending task
            taken_exclusive_resources.update(exclusive_resources)
            taken_shared_resources.update(shared_resources)

        return changed

    def iter_tasks(self):
        """Iterate over ready tasks and yield each task while holding the lock."""

        while not self.shutdown_requested:
            # When batching this query, be sure to use "pulp_created" as a cursor
            for task in Task.objects.filter(
                state__in=TASK_INCOMPLETE_STATES, unblocked_at__isnull=False
            ).order_by("pulp_created"):
                with contextlib.suppress(AdvisoryLockError), task:
                    # This code will only be called if we acquired the lock successfully
                    # The lock will be automatically be released at the end of the block
                    # Check if someone else changed the task before we got the lock
                    task.refresh_from_db()
                    if task.state == TASK_STATES.CANCELING and task.worker is None:
                        # No worker picked this task up before being canceled
                        if self.cancel_abandoned_task(task, TASK_STATES.CANCELED):
                            # Continue looking for the next task
                            # without considering this tasks resources
                            # as we just released them
                            continue
                    if task.state in [TASK_STATES.RUNNING, TASK_STATES.CANCELING]:
                        # A running task without a lock must be abandoned
                        if self.cancel_abandoned_task(
                            task, TASK_STATES.FAILED, "Worker has gone missing."
                        ):
                            # Continue looking for the next task
                            # without considering this tasks resources
                            # as we just released them
                            continue
                    # This statement is using lazy evaluation
                    if (
                        task.state == TASK_STATES.WAITING
                        and task.unblocked_at is not None
                        and self.is_compatible(task)
                    ):
                        yield task
                        # Start from the top of the Task list
                        break
            else:
                break

    def sleep(self):
        """Wait for signals on the wakeup channel while heart beating."""

        _logger.debug(_("Worker %s entering sleep state."), self.name)
        while not self.shutdown_requested and not self.wakeup:
            r, w, x = select.select(
                [self.sentinel, connection.connection], [], [], self.heartbeat_period.seconds
            )
            self.beat()
            if connection.connection in r:
                connection.connection.execute("SELECT 1")
            if self.sentinel in r:
                os.read(self.sentinel, 256)
        self.wakeup = False

    def supervise_task(self, task):
        """Call and supervise the task process while heart beating.

        This function must only be called while holding the lock for that task."""

        self.cancel_task = False
        self.task = task
        task.worker = self.worker
        task.save(update_fields=["worker"])
        cancel_state = None
        cancel_reason = None
        with TemporaryDirectory(dir=".") as task_working_dir_rel_path:
            task_process = Process(target=perform_task, args=(task.pk, task_working_dir_rel_path))
            task_process.start()
            while True:
                if cancel_state:
                    if self.task_grace_timeout != 0:
                        _logger.info("Wait for canceled task to abort.")
                    else:
                        self.task_grace_timeout = TASK_KILL_INTERVAL
                        _logger.info("Aborting current task %s due to cancelation.", task.pk)
                        os.kill(task_process.pid, signal.SIGUSR1)

                r, w, x = select.select(
                    [self.sentinel, connection.connection, task_process.sentinel],
                    [],
                    [],
                    self.heartbeat_period.seconds,
                )
                self.beat()
                if connection.connection in r:
                    connection.connection.execute("SELECT 1")
                    if self.cancel_task:
                        _logger.info(_("Received signal to cancel current task %s."), task.pk)
                        cancel_state = TASK_STATES.CANCELED
                        self.cancel_task = False
                    if self.wakeup:
                        with contextlib.suppress(AdvisoryLockError), PGAdvisoryLock(
                            TASK_UNBLOCKING_LOCK
                        ):
                            self.identify_unblocked_tasks()
                        self.wakeup = False
                if task_process.sentinel in r:
                    if not task_process.is_alive():
                        break
                if self.sentinel in r:
                    os.read(self.sentinel, 256)
                if self.shutdown_requested:
                    if self.task_grace_timeout != 0:
                        _logger.info(
                            "Worker shutdown requested, waiting for task %s to finish.", task.pk
                        )
                    else:
                        _logger.info("Aborting current task %s due to worker shutdown.", task.pk)
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
            self.notify_workers()
        self.task = None

    def handle_available_tasks(self):
        keep_looping = True
        while keep_looping and not self.shutdown_requested:
            try:
                with PGAdvisoryLock(TASK_UNBLOCKING_LOCK):
                    keep_looping = self.identify_unblocked_tasks()
            except AdvisoryLockError:
                keep_looping = True
            for task in self.iter_tasks():
                keep_looping = True
                self.supervise_task(task)

    def record_unblocked_waiting_tasks_metric(self):
        if os.getenv("PULP_OTEL_ENABLED", "").lower() != "true":
            return

        now = timezone.now()
        if now > self.last_metric_heartbeat + self.heartbeat_period:
            with contextlib.suppress(AdvisoryLockError), PGAdvisoryLock(
                TASK_METRICS_HEARTBEAT_LOCK
            ):
                # For performance reasons we aggregate these statistics on a single database call.
                unblocked_tasks_stats = (
                    Task.objects.filter(unblocked_at__isnull=False, started_at__isnull=True)
                    .annotate(unblocked_for=Value(timezone.now()) - F("unblocked_at"))
                    .aggregate(
                        longest_unblocked_waiting_time=Max(
                            "unblocked_for", default=timezone.timedelta(0)
                        ),
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
                self.handle_available_tasks()
            else:
                self.cursor.execute("LISTEN pulp_worker_wakeup")
                while not self.shutdown_requested:
                    if self.shutdown_requested:
                        break
                    self.handle_available_tasks()
                    if self.shutdown_requested:
                        break
                    self.sleep()
                self.cursor.execute("UNLISTEN pulp_worker_wakeup")
            self.cursor.execute("UNLISTEN pulp_worker_metrics_heartbeat")
            self.cursor.execute("UNLISTEN pulp_worker_cancel")
            self.shutdown()
