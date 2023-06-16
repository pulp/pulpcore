from gettext import gettext as _

import logging
import os
import random
import resource
import select
import signal
import socket
import sys
import threading
import time
import contextlib
from datetime import timedelta
from multiprocessing import Process
from tempfile import TemporaryDirectory
from packaging.version import parse as parse_version

from django.conf import settings
from django.db import connection
from django.utils import timezone
from django_guid import set_guid

from pulpcore.app.models import Worker, Task

from pulpcore.app.util import (
    configure_analytics,
    configure_cleanup,
    set_domain,
    set_current_user,
)
from pulpcore.app.role_util import get_users_with_perms

from pulpcore.constants import (
    TASK_STATES,
    TASK_INCOMPLETE_STATES,
    VAR_TMP_PULP,
)

from pulpcore.app.apps import pulp_plugin_configs
from pulpcore.exceptions import AdvisoryLockError
from pulpcore.tasking.storage import WorkerDirectory
from pulpcore.tasking.tasks import dispatch_scheduled_tasks, execute_task
from pulpcore.tasking.util import _delete_incomplete_resources


_logger = logging.getLogger(__name__)
random.seed()

# Number of heartbeats for a task to finish on graceful worker shutdown (approx)
TASK_GRACE_INTERVAL = 3
# Number of heartbeats between attempts to kill the subprocess (approx)
TASK_KILL_INTERVAL = 1
# Number of heartbeats between cleaning up worker processes (approx)
WORKER_CLEANUP_INTERVAL = 100
# Randomly chosen
TASK_SCHEDULING_LOCK = 42


def startup_hook():
    configure_analytics()
    configure_cleanup()


class PGAdvisoryLock:
    """
    A context manager that will hold a postgres advisory lock non-blocking.

    The locks can be chosen from a lock group to avoid collisions. They will never collide with the
    locks used for tasks.
    """

    def __init__(self, lock, lock_group=0):
        self.lock_group = lock_group
        self.lock = lock

    def __enter__(self):
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_try_advisory_lock(%s, %s)", [self.lock_group, self.lock])
            acquired = cursor.fetchone()[0]
        if not acquired:
            raise AdvisoryLockError("Could not acquire lock.")
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_unlock(%s, %s)", [self.lock_group, self.lock])
            released = cursor.fetchone()[0]
        if not released:
            raise RuntimeError("Lock not held.")


class NewPulpWorker:
    def __init__(self):
        # Notification states from several signal handlers
        self.shutdown_requested = False
        self.wakeup = False
        self.cancel_task = False

        self.task = None
        self.name = f"{os.getpid()}@{socket.getfqdn()}"
        self.heartbeat_period = settings.WORKER_TTL / 3
        self.versions = {app.label: app.version for app in pulp_plugin_configs()}
        self.cursor = connection.cursor()
        self.worker = self.handle_worker_heartbeat()
        self.task_grace_timeout = 0
        self.worker_cleanup_countdown = random.randint(
            WORKER_CLEANUP_INTERVAL / 10, WORKER_CLEANUP_INTERVAL
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
        qs = Worker.objects.missing_workers(age=timedelta(days=7))
        if qs:
            for worker in qs:
                _logger.info(_("Clean missing worker %s."), worker.name)
            qs.delete()

    def beat(self):
        if self.worker.last_heartbeat < timezone.now() - timedelta(seconds=self.heartbeat_period):
            self.worker = self.handle_worker_heartbeat()
            if self.task_grace_timeout > 0:
                self.task_grace_timeout -= 1
            self.worker_cleanup_countdown -= 1
            if self.worker_cleanup_countdown <= 0:
                self.worker_cleanup_countdown = WORKER_CLEANUP_INTERVAL
                self.worker_cleanup()
            with contextlib.suppress(AdvisoryLockError), PGAdvisoryLock(TASK_SCHEDULING_LOCK):
                dispatch_scheduled_tasks()

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
        _delete_incomplete_resources(task)
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

    def iter_tasks(self):
        """Iterate over ready tasks and yield each task while holding the lock."""

        while not self.shutdown_requested:
            taken_exclusive_resources = set()
            taken_shared_resources = set()
            # When batching this query, be sure to use "pulp_created" as a cursor
            for task in Task.objects.filter(state__in=TASK_INCOMPLETE_STATES).order_by(
                "pulp_created"
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
                        and self.is_compatible(task)
                        # No exclusive resource taken?
                        and not any(
                            resource in taken_exclusive_resources
                            or resource in taken_shared_resources
                            for resource in exclusive_resources
                        )
                        # No shared resource exclusively taken?
                        and not any(
                            resource in taken_exclusive_resources for resource in shared_resources
                        )
                    ):
                        yield task
                        # Start from the top of the Task list
                        break

                # Record the resources of the pending task we didn't get
                taken_exclusive_resources.update(exclusive_resources)
                taken_shared_resources.update(shared_resources)
            else:
                # If we got here, there is nothing to do
                break

    def sleep(self):
        """Wait for signals on the wakeup channel while heart beating."""

        _logger.debug(_("Worker %s entering sleep state."), self.name)
        while not self.shutdown_requested and not self.wakeup:
            r, w, x = select.select(
                [self.sentinel, connection.connection], [], [], self.heartbeat_period
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
            task_process = Process(target=_perform_task, args=(task.pk, task_working_dir_rel_path))
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
                    self.heartbeat_period,
                )
                self.beat()
                if connection.connection in r:
                    connection.connection.execute("SELECT 1")
                    if self.cancel_task:
                        _logger.info(_("Received signal to cancel current task %s."), task.pk)
                        cancel_state = TASK_STATES.CANCELED
                        self.cancel_task = False
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

    def run_forever(self):
        with WorkerDirectory(self.name):
            signal.signal(signal.SIGINT, self._signal_handler)
            signal.signal(signal.SIGTERM, self._signal_handler)
            signal.signal(signal.SIGHUP, self._signal_handler)
            # Subscribe to pgsql channels
            connection.connection.add_notify_handler(self._pg_notify_handler)
            self.cursor.execute("LISTEN pulp_worker_wakeup")
            self.cursor.execute("LISTEN pulp_worker_cancel")
            while not self.shutdown_requested:
                for task in self.iter_tasks():
                    self.supervise_task(task)
                if not self.shutdown_requested:
                    self.sleep()
            self.cursor.execute("UNLISTEN pulp_worker_cancel")
            self.cursor.execute("UNLISTEN pulp_worker_wakeup")
            self.shutdown()


def write_memory_usage(task_pk):
    taskdata_dir = VAR_TMP_PULP / str(task_pk)
    taskdata_dir.mkdir(parents=True, exist_ok=True)
    memory_file_dir = taskdata_dir / "memory.datum"
    _logger.info("Writing task memory data to {}".format(memory_file_dir))

    with open(memory_file_dir, "w") as file:
        file.write("# Seconds\tMemory in MB\n")
        seconds = 0
        while True:
            current_mb_in_use = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024
            file.write(f"{seconds}\t{current_mb_in_use:.2f}\n")
            file.flush()
            time.sleep(5)
            seconds += 5


def child_signal_handler(sig, frame):
    # Reset signal handlers to default
    # If you kill the process a second time it's not graceful anymore.
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    signal.signal(signal.SIGTERM, signal.SIG_DFL)
    signal.signal(signal.SIGHUP, signal.SIG_DFL)
    signal.signal(signal.SIGUSR1, signal.SIG_DFL)

    if sig == signal.SIGUSR1:
        sys.exit()


def _perform_task(task_pk, task_working_dir_rel_path):
    """Setup the environment to handle a task and execute it.
    This must be called as a subprocess, while the parent holds the advisory lock."""
    signal.signal(signal.SIGINT, child_signal_handler)
    signal.signal(signal.SIGTERM, child_signal_handler)
    signal.signal(signal.SIGHUP, child_signal_handler)
    signal.signal(signal.SIGUSR1, child_signal_handler)
    if settings.TASK_DIAGNOSTICS:
        # It would be better to have this recording happen in the parent process instead of here
        # https://github.com/pulp/pulpcore/issues/2337
        normal_thread = threading.Thread(target=write_memory_usage, args=(task_pk,), daemon=True)
        normal_thread.start()
    # All processes need to create their own postgres connection
    connection.connection = None
    task = Task.objects.select_related("pulp_domain").get(pk=task_pk)
    user = get_users_with_perms(task, with_group_users=False).first()
    # Set current contexts
    set_guid(task.logging_cid)
    set_current_user(user)
    set_domain(task.pulp_domain)
    os.chdir(task_working_dir_rel_path)
    execute_task(task)
