import asyncio
import importlib
import json
import logging
import os
import socket
import sys
import threading
import socket
import time

import click
from rq import Queue
from rq.worker import Worker

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "pulpcore.app.settings")
django.setup()

from django.conf import settings  # noqa: E402: module level not at top of file
from django.db import connection  # noqa: E402: module level not at top of file
from guardian.shortcuts import get_users_with_perms  # noqa: E402: module level not at top of file
from django_currentuser.middleware import (  # noqa: E402: module level not at top of file
    _set_current_user,
)
from django_guid.middleware import GuidMiddleware  # noqa: E402: module level not at top of file

from pulpcore.app.settings import WORKER_TTL  # noqa: E402: module level not at top of file

from pulpcore.app.models import Task  # noqa: E402: module level not at top of file

from pulpcore.constants import (  # noqa: E402: module level not at top of file
    TASK_CHOICES,
    TASK_FINAL_STATES,
    TASK_STATES,
)

from pulpcore.tasking.constants import (  # noqa: E402: module level not at top of file
    TASKING_CONSTANTS,
)
from pulpcore.tasking.storage import (  # noqa: E402: module level not at top of file
    TaskWorkingDirectory,
    WorkerDirectory,
)
from pulpcore.tasking.worker_watcher import (  # noqa: E402
    check_worker_processes,
    check_and_cancel_missing_tasks,
    handle_worker_heartbeat,
    mark_worker_offline,
)


_logger = logging.getLogger(__name__)


class PulpWorker(Worker):
    """
    A Pulp worker for both the resource manager and generic workers

    This worker is customized in the following ways:

        * Replaces the string '%h' in the worker name with the fqdn
        * If the name starts with 'reserved-resource-worker' the worker ignores any other Queue
          configuration and only subscribes to a queue of the same name as the worker name
        * If the name starts with 'resource-manager' the worker ignores any other Queue
          configuration and only subscribes to the 'resource-manager' queue
        * Sets the worker TTL
        * Supports the killing of a job that is already running
        * Closes the database connection before forking so it is not process shared
    """

    # Do not print "Result is kept for XXX seconds" after each job
    log_result_lifespan = False

    def __init__(self, queues, **kwargs):

        if kwargs["name"]:
            kwargs["name"] = kwargs["name"].replace("%h", socket.getfqdn())
        else:
            kwargs["name"] = "{pid}@{hostname}".format(pid=os.getpid(), hostname=socket.getfqdn())

        if kwargs["name"] == TASKING_CONSTANTS.RESOURCE_MANAGER_WORKER_NAME:
            queues = [Queue("resource-manager", connection=kwargs["connection"])]
            self.is_resource_manager = True
        else:
            queues = [Queue(kwargs["name"], connection=kwargs["connection"])]
            self.is_resource_manager = False

        kwargs["default_worker_ttl"] = WORKER_TTL
        kwargs["job_monitoring_interval"] = TASKING_CONSTANTS.JOB_MONITORING_INTERVAL

        return super().__init__(queues, **kwargs)

    def execute_job(self, *args, **kwargs):
        """
        Close the database connection before forking, so that it is not shared
        """
        django.db.connections.close_all()
        super().execute_job(*args, **kwargs)

    def perform_job(self, job, queue):
        """
        Set the :class:`pulpcore.app.models.Task` to running and init logging.

        This method is called by the worker's work horse thread (the forked child) just before the
        task begins executing.

        Args:
            job (rq.job.Job): The job to perform
            queue (rq.queue.Queue): The Queue associated with the job
        """
        try:
            task = Task.objects.get(pk=job.get_id())
        except Task.DoesNotExist:
            pass
        else:
            task.set_running()
            user = get_users_with_perms(task).first()
            _set_current_user(user)
            GuidMiddleware.set_guid(task.logging_cid)

        with TaskWorkingDirectory(job):
            return super().perform_job(job, queue)

    def handle_job_failure(self, job, **kwargs):
        """
        Set the :class:`pulpcore.app.models.Task` to failed and record the exception.

        This method is called by rq to handle a job failure.

        Args:
            job (rq.job.Job): The job that experienced the failure
            kwargs (dict): Unused parameters
        """
        try:
            task = Task.objects.get(pk=job.get_id())
            task.release_resources()
            exc_type, exc, tb = sys.exc_info()
            res = super().handle_job_failure(job, **kwargs)
            # job "is_stopped" state determined during super().handle_job_failure()
            if not job.is_stopped:
                # stopped jobs go onto the failed queue in RQ, so we need to ignore those
                # to avoid overwriting the task status
                task.set_failed(exc, tb)
            return res
        except Task.DoesNotExist:
            return super().handle_job_failure(job, **kwargs)

    def handle_job_success(self, job, queue, started_job_registry):
        """
        Set the :class:`pulpcore.app.models.Task` to completed.

        This method is called by rq to handle a job success.

        Args:
            job (rq.job.Job): The job that experienced the success
            queue (rq.queue.Queue): The Queue associated with the job
            started_job_registry (rq.registry.StartedJobRegistry): The RQ registry of started jobs
        """
        try:
            task = Task.objects.get(pk=job.get_id())
            task.release_resources()
        except Task.DoesNotExist:
            pass
        else:
            task.set_completed()

        return super().handle_job_success(job, queue, started_job_registry)

    def register_birth(self, *args, **kwargs):
        """
        Handle the birth of a RQ worker.

        This creates the working directory and removes any vestige records from a previous worker
        with the same name.

        Args:
            args (tuple): unused positional arguments
            kwargs (dict): unused keyword arguments
        """
        mark_worker_offline(self.name, normal_shutdown=True)
        working_dir = WorkerDirectory(self.name)
        working_dir.delete()
        working_dir.create()
        return super().register_birth(*args, **kwargs)

    def heartbeat(self, *args, **kwargs):
        """
        Handle the heartbeat of a RQ worker.

        This writes the heartbeat records to the :class:`pulpcore.app.models.Worker` records.

        Args:
            args (tuple): unused positional arguments
            kwargs (dict): unused keyword arguments
        """
        handle_worker_heartbeat(self.name)
        check_worker_processes()
        if self.is_resource_manager:
            check_and_cancel_missing_tasks()

        return super().heartbeat(*args, **kwargs)

    def handle_warm_shutdown_request(self, *args, **kwargs):
        """
        Handle the warm shutdown of a RQ worker.

        This cleans up any leftover records and marks the :class:`pulpcore.app.models.Worker`
        record as being a clean shutdown.

        Args:
            args (tuple): unused positional arguments
            kwargs (dict): unused keyword arguments
        """
        mark_worker_offline(self.name, normal_shutdown=True)
        return super().handle_warm_shutdown_request(*args, **kwargs)


@click.command()
def worker():
    """A Pulp worker."""
    NewPulpWorker().run_forever()


class NewPulpWorker:
    def __init__(self):
        self.name = f"{os.getpid()}@{socket.getfqdn()}"

    def heartbeat_loop(self):
        seconds_between_heartbeats = settings.WORKER_TTL / 3
        while True:
            handle_worker_heartbeat(self.name)
            time.sleep(seconds_between_heartbeats)

    def get_resources_for_running_tasks(self):
        taken_resources = set()
        waiting_tasks = Task.objects.filter(state=TASK_STATES.RUNNING)
        for resources in waiting_tasks.values_list('new_reserved_resources_record', flat=True):
            for resource in resources:
                taken_resources.add(resource)
        return taken_resources

    def task_has_all_resources_available(self, task, taken_resources):
        all_resources_free = True
        for required_resource in task.new_reserved_resources_record:
            if required_resource in taken_resources:
                all_resources_free = False
                break
        return all_resources_free

    def lock_task_resources(self, task):
        with connection.cursor() as cursor:
            for required_resource in task.new_reserved_resources_record:
                cursor.execute("SELECT pg_try_advisory_lock(hashtext(%s));", [required_resource])
                acquired = cursor.fetchone()[0]
                if not acquired:
                    cursor.execute("SELECT pg_advisory_unlock_all();")
                    return False
            return True

    def run_forever(self):
        t = threading.Thread(target=self.heartbeat_loop)
        t.start()
        while True:
            taken_resources = self.get_resources_for_running_tasks()
            waiting_tasks = Task.objects.filter(state=TASK_STATES.WAITING).order_by('pulp_created')
            for task in waiting_tasks:
                if self.task_has_all_resources_available(task, taken_resources):
                    all_locks_acquired = self.lock_task_resources(task)
                    if all_locks_acquired:
                        self.perform_task(task)
                    else:
                        for required_resources in task.new_reserved_resources_record:
                            taken_resources.add(required_resources)
                        continue
            time.sleep(0.2)

    def perform_task(self, task):
        module_name, attribute = task.name.rsplit('.', 1)
        module = importlib.import_module(module_name)
        self.func = getattr(module, attribute)
        task.set_running()
        try:
            self.execute(task)
        except Exception:
            exc_type, exc, tb = sys.exc_info()
            task.set_failed(exc, tb)
        else:
            task.set_completed()
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_advisory_unlock_all();")

    def execute(self, task):
        args = json.loads(task.args)
        kwargs = json.loads(task.kwargs)
        if args is None:
            args = ()
        if kwargs is None:
            kwargs = {}
        result = self.func(*args, **kwargs)
        if asyncio.iscoroutine(result):
            loop = asyncio.get_event_loop()
            coro_result = loop.run_until_complete(result)
            return coro_result
