import asyncio
import importlib
import json
import logging
import os
import select
import socket
import sys
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
from guardian.shortcuts import get_users_with_perms  # noqa: E402: module level not at top of file
from django_currentuser.middleware import (  # noqa: E402: module level not at top of file
    _set_current_user,
)
from django_guid.middleware import GuidMiddleware  # noqa: E402: module level not at top of file

from pulpcore.app.models import Task  # noqa: E402: module level not at top of file

from pulpcore.constants import (  # noqa: E402: module level not at top of file
    TASK_STATES,
    TASK_INCOMPLETE_STATES,
)

from pulpcore.exceptions import AdvisoryLockError  # noqa: E402: module level not at top of file
from pulpcore.tasking.storage import WorkerDirectory  # noqa: E402: module level not at top of file
from pulpcore.tasking.util import _delete_incomplete_resources  # noqa: E402
from pulpcore.tasking.worker_watcher import handle_worker_heartbeat  # noqa: E402


_logger = logging.getLogger(__name__)


class NewPulpWorker:
    def __init__(self):
        self.name = f"{os.getpid()}@{socket.getfqdn()}"
        self.heartbeat_period = settings.WORKER_TTL / 3
        self.cursor = connection.cursor()
        self.worker = handle_worker_heartbeat(self.name)

    def beat(self):
        if self.worker.last_heartbeat < timezone.now() - timedelta(seconds=self.heartbeat_period):
            self.worker = handle_worker_heartbeat(self.name)

    def notify_workers(self):
        self.cursor.execute("NOTIFY pulp_worker_wakeup")

    def cancel_abandoned_task(self, task):
        """Cancel and clean up an abandoned task.

        This function must only be called while holding the lock for that task.

        Return ``True`` if the task was actually canceled, ``False`` otherwise.
        """
        # A task is considered abandoned when in running state, but no worker holds its lock
        _logger.info(f"Canceling Task {task.pk}")
        Task.objects.filter(pk=task.pk, state=TASK_STATES.RUNNING).update(
            state=TASK_STATES.CANCELING
        )
        task.refresh_from_db()
        if task.state == TASK_STATES.CANCELING:
            _delete_incomplete_resources(task)
            if task.reserved_resources_record:
                self.notify_workers()
                Task.objects.filter(pk=task.pk, state=TASK_STATES.CANCELING).update(
                    state=TASK_STATES.CANCELED
                )
            return True
        return False

    def iter_tasks(self):
        """Iterate over ready tasks and yield each task while holding the lock."""

        while True:
            taken_resources = set()
            # When batching this query, be sure to use "pulp_created" as a cursor
            for task in Task.objects.filter(state__in=TASK_INCOMPLETE_STATES).order_by(
                "pulp_created"
            ):
                reserved_resources_record = task.reserved_resources_record or []
                with suppress(AdvisoryLockError), task:
                    # This code will only be called if we acquired the lock successfully
                    # The lock will be automatically be released at the end of the block
                    # Check if someone else changed the task before we got the lock
                    task.refresh_from_db()
                    if task.state in [TASK_STATES.RUNNING, TASK_STATES.CANCELING]:
                        # A running task without a lock must be abandoned
                        if self.cancel_abandoned_task(task):
                            # Continue looking for the next task
                            # without considering this tasks resources
                            # as we just released them
                            continue
                    if task.state == TASK_STATES.WAITING and not any(
                        resource in taken_resources for resource in reserved_resources_record
                    ):
                        yield task
                        # Start from the top of the Task list
                        break
                # Record the resources of the pending task we didn't get
                taken_resources.update(reserved_resources_record)
            else:
                # If we got here, there is nothing to do
                break

    def sleep(self):
        """Wait for signals on the wakeup channel while heart beating."""

        _logger.info(f"Worker {self.name} entering sleep state.")
        # Subscribe to "pulp_worker_wakeup"
        self.cursor.execute("LISTEN pulp_worker_wakeup")
        while True:
            r, w, x = select.select([connection.connection], [], [], self.heartbeat_period)
            self.beat()
            if r:
                connection.connection.poll()
                if any(
                    (
                        item.channel == "pulp_worker_wakeup"
                        for item in connection.connection.notifies
                    )
                ):
                    connection.connection.notifies.clear()
                    break
        self.cursor.execute("UNLISTEN pulp_worker_wakeup")

    def supervise_task(self, task):
        """Call and supervise the task process while heart beating.

        This function must only be called while holding the lock for that task."""

        self.cursor.execute("LISTEN pulp_worker_cancel")
        task.worker = self.worker
        task.save(update_fields=["worker"])
        task_process = Process(target=_perform_task, args=(task.pk,))
        task_process.start()
        while True:
            r, w, x = select.select(
                [connection.connection, task_process.sentinel], [], [], self.heartbeat_period
            )
            self.beat()
            if r:
                connection.connection.poll()
                if any(
                    (
                        item.channel == "pulp_worker_cancel" and item.payload == str(task.pk)
                        for item in connection.connection.notifies
                    )
                ):
                    connection.connection.notifies.clear()
                    _logger.info(f"Received signal to cancel task {task.pk}.")
                    task_process.terminate()
                    break
                if not task_process.is_alive():
                    break
        task_process.join()
        if task.reserved_resources_record:
            self.notify_workers()
        self.cursor.execute("UNLISTEN pulp_worker_cancel")

    def run_forever(self):
        with WorkerDirectory(self.name):
            while True:
                for task in self.iter_tasks():
                    try:
                        # Workaround to block all other workers
                        if task.name == "pulpcore.app.tasks.orphan.orphan_cleanup":
                            suffix = ""
                        else:
                            suffix = "_shared"
                        self.cursor.execute(f"SELECT pg_advisory_lock{suffix}(1234)")
                        self.supervise_task(task)
                    finally:
                        self.cursor.execute(f"SELECT pg_advisory_unlock{suffix}(1234)")
                self.sleep()


def _perform_task(task_pk):
    """Setup the environment to handle a task and execute it.
    This must be called as a subprocess, while the parent holds the advisory lock."""
    # All processes need to create their own postgres connection
    connection.connection = None
    task = Task.objects.get(pk=task_pk)
    task.set_running()
    # Store the task id in the environment for `Task.current()`.
    os.environ["PULP_TASK_ID"] = str(task.pk)
    user = get_users_with_perms(task).first()
    _set_current_user(user)
    GuidMiddleware.set_guid(task.logging_cid)
    try:
        _logger.info("Starting task {}".format(task.pk))

        # Execute task
        module_name, function_name = task.name.rsplit(".", 1)
        module = importlib.import_module(module_name)
        func = getattr(module, function_name)
        args = json.loads(task.args) or ()
        kwargs = json.loads(task.kwargs) or {}
        with TemporaryDirectory(dir="."):
            result = func(*args, **kwargs)
            if asyncio.iscoroutine(result):
                _logger.info("Task is coroutine {}".format(task.pk))
                loop = asyncio.get_event_loop()
                loop.run_until_complete(result)

    except Exception:
        exc_type, exc, tb = sys.exc_info()
        task.set_failed(exc, tb)
        _logger.info("Task failed {}".format(task.pk))
    else:
        task.set_completed()
        _logger.info("Task completed {}".format(task.pk))
    os.environ.pop("PULP_TASK_ID")
