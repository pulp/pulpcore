from gettext import gettext as _

import asyncio
import importlib
import logging
import os
import random
import select
import signal
import socket
import sys
import traceback
from contextlib import suppress
from datetime import timedelta
from multiprocessing import Process
from tempfile import TemporaryDirectory

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "pulpcore.app.settings")
django.setup()

from django.conf import settings  # noqa: E402: module level not at top of file
from django.db import connection  # noqa: E402: module level not at top of file
from django.utils import timezone  # noqa: E402: module level not at top of file
from django_currentuser.middleware import (  # noqa: E402: module level not at top of file
    _set_current_user,
)
from django_guid import set_guid  # noqa: E402: module level not at top of file

from pulpcore.app.models import Worker, Task  # noqa: E402: module level not at top of file

from pulpcore.app.role_util import (  # noqa: E402: module level not at top of file
    get_users_with_perms,
)

from pulpcore.constants import (  # noqa: E402: module level not at top of file
    TASK_STATES,
    TASK_INCOMPLETE_STATES,
)

from pulpcore.exceptions import AdvisoryLockError  # noqa: E402: module level not at top of file
from pulpcore.tasking.storage import WorkerDirectory  # noqa: E402: module level not at top of file
from pulpcore.tasking.tasks import dispatch_scheduled_tasks  # noqa: E402
from pulpcore.tasking.util import _delete_incomplete_resources  # noqa: E402


_logger = logging.getLogger(__name__)
random.seed()

TASK_GRACE_INTERVAL = 3
WORKER_CLEANUP_INTERVAL = 100


class PGAdvisoryLock:
    def __init__(self, lock, lock_group=0):
        self.lock_group = lock_group
        self.lock = lock

    def __enter__(self):
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_try_advisory_lock(%s, %s);", [self.lock_group, self.lock])
            acquired = cursor.fetchone()[0]
        if not acquired:
            raise AdvisoryLockError("Could not acquire lock.")
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_unlock(%s, %s);", [self.lock_group, self.lock])
            released = cursor.fetchone()[0]
        if not released:
            raise RuntimeError("Lock not held.")


def handle_worker_heartbeat(worker_name):
    """
    This is a generic function for updating worker heartbeat records.

    Existing Worker objects are searched for one to update. If an existing one is found, it is
    updated. Otherwise a new Worker entry is created. Logging at the info level is also done.

    Args:
        worker_name (str): The hostname of the worker
    """
    worker, created = Worker.objects.get_or_create(name=worker_name)

    if created:
        _logger.info(_("New worker '{name}' discovered").format(name=worker_name))
    elif worker.online is False:
        _logger.info(_("Worker '{name}' is back online.").format(name=worker_name))

    worker.save_heartbeat()

    msg = _("Worker heartbeat from '{name}' at time {timestamp}").format(
        timestamp=worker.last_heartbeat, name=worker_name
    )

    _logger.debug(msg)

    return worker


class NewPulpWorker:
    def __init__(self):
        self.shutdown_requested = False
        self.name = f"{os.getpid()}@{socket.getfqdn()}"
        self.heartbeat_period = settings.WORKER_TTL / 3
        self.cursor = connection.cursor()
        self.worker = handle_worker_heartbeat(self.name)
        self.task_grace_timeout = 0
        self.worker_cleanup_countdown = random.randint(
            WORKER_CLEANUP_INTERVAL / 10, WORKER_CLEANUP_INTERVAL
        )

        # Add a file descriptor to trigger select on signals
        self.sentinel, sentinel_w = os.pipe()
        os.set_blocking(self.sentinel, False)
        os.set_blocking(sentinel_w, False)
        signal.set_wakeup_fd(sentinel_w)

    def _signal_handler(self, thesignal, frame):
        # Reset signal handlers to default
        # If you kill the process a second time it's not graceful anymore.
        signal.signal(signal.SIGINT, signal.SIG_DFL)
        signal.signal(signal.SIGTERM, signal.SIG_DFL)

        _logger.info(_("Worker %s was requested to shut down."), self.name)

        self.shutdown_requested = True

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
            self.worker = handle_worker_heartbeat(self.name)
            if self.shutdown_requested:
                self.task_grace_timeout -= 1
            self.worker_cleanup_countdown -= 1
            if self.worker_cleanup_countdown <= 0:
                self.worker_cleanup_countdown = WORKER_CLEANUP_INTERVAL
                self.worker_cleanup()
            with suppress(AdvisoryLockError), PGAdvisoryLock(42):
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
        Task.objects.filter(pk=task.pk, state=TASK_STATES.RUNNING).update(
            state=TASK_STATES.CANCELING
        )
        task.refresh_from_db()
        if task.state == TASK_STATES.CANCELING:
            if reason:
                _logger.info(
                    _("Cleaning up task %s and marking as %s. Reason: %s"),
                    task.pk,
                    final_state,
                    reason,
                )
            else:
                _logger.info(_("Cleaning up task %s and marking as %s."), task.pk, final_state)
            _delete_incomplete_resources(task)
            if task.reserved_resources_record:
                self.notify_workers()
            task_data = {
                "state": final_state,
                "finished_at": timezone.now(),
            }
            if reason:
                task_data["error"] = {"reason": reason}
            Task.objects.filter(pk=task.pk, state=TASK_STATES.CANCELING).update(**task_data)
            return True
        return False

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
                with suppress(AdvisoryLockError), task:
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
        wakeup = False
        while not self.shutdown_requested:
            # Handle all notifications before sleeping in `select`
            while connection.connection.notifies:
                item = connection.connection.notifies.pop(0)
                if item.channel == "pulp_worker_wakeup":
                    _logger.debug(_("Worker %s received wakeup call."), self.name)
                    wakeup = True
                # ignore all other notifications
            if wakeup:
                break

            r, w, x = select.select(
                [self.sentinel, connection.connection], [], [], self.heartbeat_period
            )
            self.beat()
            if connection.connection in r:
                connection.connection.poll()
            if self.sentinel in r:
                os.read(self.sentinel, 256)

    def supervise_task(self, task):
        """Call and supervise the task process while heart beating.

        This function must only be called while holding the lock for that task."""

        self.task_grace_timeout = TASK_GRACE_INTERVAL
        task.worker = self.worker
        task.save(update_fields=["worker"])
        cancel_state = None
        cancel_reason = None
        with TemporaryDirectory(dir=".") as task_working_dir_rel_path:
            task_process = Process(target=_perform_task, args=(task.pk, task_working_dir_rel_path))
            task_process.start()
            while True:
                # Handle all notifications before sleeping in `select`
                while connection.connection.notifies:
                    item = connection.connection.notifies.pop(0)
                    if item.channel == "pulp_worker_cancel" and item.payload == str(task.pk):
                        _logger.info(_("Received signal to cancel current task %s."), task.pk)
                        os.kill(task_process.pid, signal.SIGUSR1)
                        cancel_state = TASK_STATES.CANCELED
                    # ignore all other notifications
                if cancel_state:
                    break

                r, w, x = select.select(
                    [self.sentinel, connection.connection, task_process.sentinel],
                    [],
                    [],
                    self.heartbeat_period,
                )
                self.beat()
                if connection.connection in r:
                    connection.connection.poll()
                if task_process.sentinel in r:
                    if not task_process.is_alive():
                        break
                if self.sentinel in r:
                    os.read(self.sentinel, 256)
                if self.shutdown_requested:
                    if self.task_grace_timeout > 0:
                        _logger.info(
                            _("Worker shutdown requested, waiting for task %s to finish."), task.pk
                        )
                    else:
                        _logger.info(_("Aborting current task %s due to worker shutdown."), task.pk)
                        os.kill(task_process.pid, signal.SIGUSR1)
                        cancel_state = TASK_STATES.FAILED
                        cancel_reason = "Aborted during worker shutdown."
                        break
            task_process.join()
            if not cancel_state and task_process.exitcode != 0:
                _logger.warn(
                    _("Task process for %s exited with non zero exitcode %i."),
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

    def run_forever(self):
        with WorkerDirectory(self.name):
            signal.signal(signal.SIGINT, self._signal_handler)
            signal.signal(signal.SIGTERM, self._signal_handler)
            # Subscribe to pgsql channels
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


def child_signal_handler(sig, frame):
    # Reset signal handlers to default
    # If you kill the process a second time it's not graceful anymore.
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    signal.signal(signal.SIGTERM, signal.SIG_DFL)
    signal.signal(signal.SIGUSR1, signal.SIG_DFL)

    if sig == signal.SIGUSR1:
        sys.exit()


def _perform_task(task_pk, task_working_dir_rel_path):
    """Setup the environment to handle a task and execute it.
    This must be called as a subprocess, while the parent holds the advisory lock."""
    signal.signal(signal.SIGINT, child_signal_handler)
    signal.signal(signal.SIGTERM, child_signal_handler)
    signal.signal(signal.SIGUSR1, child_signal_handler)
    # All processes need to create their own postgres connection
    connection.connection = None
    task = Task.objects.get(pk=task_pk)
    task.set_running()
    # Store the task id in the environment for `Task.current()`.
    os.environ["PULP_TASK_ID"] = str(task.pk)
    user = get_users_with_perms(task, with_group_users=False).first()
    _set_current_user(user)
    set_guid(task.logging_cid)
    try:
        _logger.info(_("Starting task %s"), task.pk)

        # Execute task
        module_name, function_name = task.name.rsplit(".", 1)
        module = importlib.import_module(module_name)
        func = getattr(module, function_name)
        args = task.args or ()
        kwargs = task.kwargs or {}
        os.chdir(task_working_dir_rel_path)
        result = func(*args, **kwargs)
        if asyncio.iscoroutine(result):
            _logger.debug(_("Task is coroutine %s"), task.pk)
            loop = asyncio.get_event_loop()
            loop.run_until_complete(result)

    except Exception:
        exc_type, exc, tb = sys.exc_info()
        task.set_failed(exc, tb)
        _logger.info(_("Task %s failed (%s)"), task.pk, exc)
        _logger.info("\n".join(traceback.format_list(traceback.extract_tb(tb))))
    else:
        task.set_completed()
        _logger.info(_("Task completed %s"), task.pk)
    os.environ.pop("PULP_TASK_ID")
