import logging
import os
import socket
import sys

from rq import Queue
from rq.worker import Worker


import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "pulpcore.app.settings")
django.setup()

from guardian.shortcuts import get_users_with_perms  # noqa: E402: module level not at top of file
from django_currentuser.middleware import (  # noqa: E402: module level not at top of file
    _set_current_user,
)
from django_guid.middleware import GuidMiddleware  # noqa: E402: module level not at top of file

from pulpcore.app import settings  # noqa: E402: module level not at top of file
from pulpcore.app.settings import WORKER_TTL  # noqa: E402: module level not at top of file

from pulpcore.app.models import Task  # noqa: E402: module level not at top of file

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

        if settings.USE_NEW_WORKER_TYPE:
            raise NotImplementedError("This worker is not supposed to run with new style tasks.")

        if kwargs.get("name"):
            kwargs["name"] = kwargs["name"].replace("%h", socket.getfqdn())
        else:
            kwargs["name"] = "{pid}@{hostname}".format(pid=os.getpid(), hostname=socket.getfqdn())

        if kwargs["name"] == TASKING_CONSTANTS.RESOURCE_MANAGER_WORKER_NAME:
            queues = [Queue("resource-manager", connection=kwargs.get("connection"))]
            self.is_resource_manager = True
        else:
            queues = [Queue(kwargs["name"], connection=kwargs.get("connection"))]
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
