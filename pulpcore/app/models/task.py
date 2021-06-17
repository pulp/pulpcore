"""
Django models related to the Tasking system
"""
import logging
import traceback
import os
from contextlib import suppress
from datetime import timedelta
from gettext import gettext as _
from hashlib import blake2s

from django.contrib.postgres.fields import JSONField, ArrayField
from django.db import connection, models
from django.db.utils import IntegrityError
from django.utils import timezone
from django.conf import settings
from rq.job import get_current_job

from pulpcore.app.models import (
    AutoAddObjPermsMixin,
    AutoDeleteObjPermsMixin,
    BaseModel,
    GenericRelationModel,
)
from pulpcore.constants import TASK_CHOICES, TASK_FINAL_STATES, TASK_STATES
from pulpcore.exceptions import AdvisoryLockError, exception_to_dict
from pulpcore.tasking.constants import TASKING_CONSTANTS
from pulpcore.app.loggers import deprecation_logger

_logger = logging.getLogger(__name__)


class ReservedResource(BaseModel):
    """
    Resources that have been reserved

    Fields:

        resource (models.TextField): The url of the resource reserved for the task.

    Relations:

        task (models.ForeignKey): The task associated with this reservation
        worker (models.ForeignKey): The worker associated with this reservation
    """

    resource = models.TextField(unique=True)

    tasks = models.ManyToManyField(
        "Task", related_name="reserved_resources", through="TaskReservedResource"
    )
    worker = models.ForeignKey("Worker", related_name="reservations", on_delete=models.CASCADE)


class TaskReservedResource(BaseModel):
    """
    Association between a Task and its ReservedResources.

    Prevents the task from being deleted if it has any ReservedResource(s).

    Fields:

        created (models.DatetimeField): When the association was created.

    Relations:

        task (models.ForeignKey): The associated task.
        resource (models.ForeignKey): The associated resource.
    """

    resource = models.ForeignKey("ReservedResource", on_delete=models.PROTECT)
    task = models.ForeignKey("Task", on_delete=models.PROTECT)


class WorkerManager(models.Manager):
    def online_workers(self):
        """
        Returns a queryset of workers meeting the criteria to be considered 'online'

        To be considered 'online', a worker must have a recent heartbeat timestamp and must not
        have the 'gracefully_stopped' flag set to True. "Recent" is defined here as "within
        the pulp process timeout interval".

        Returns:
            :class:`django.db.models.query.QuerySet`:  A query set of the Worker objects which
                are considered by Pulp to be 'online'.
        """
        now = timezone.now()
        age_threshold = now - timedelta(seconds=settings.WORKER_TTL)

        return self.filter(last_heartbeat__gte=age_threshold, gracefully_stopped=False)

    def missing_workers(self):
        """
        Returns a queryset of workers meeting the criteria to be considered 'missing'

        To be considered missing, a worker must have a stale timestamp and must not
        have the 'gracefully_stopped' flag set to True.  Stale is defined here as
        "beyond the pulp process timeout interval".

        Returns:
            :class:`django.db.models.query.QuerySet`:  A query set of the Worker objects which
                are considered by Pulp to be 'missing'.
        """
        now = timezone.now()
        age_threshold = now - timedelta(seconds=settings.WORKER_TTL)

        return self.filter(last_heartbeat__lt=age_threshold, gracefully_stopped=False)

    def dirty_workers(self):
        """
        Returns a queryset of workers meeting the criteria to be considered 'dirty'

        To be considered dirty, a worker must have a stale timestamp and must have both the
        'cleaned_up' and 'gracefully_stopped' flags set to false.  Stale is defined here as
        "beyond the pulp process timeout interval".

        This is intended to be used to determine which workers need to be cleaned up after
        following an improper 'hard' shutdown.

        Returns:
            :class:`django.db.models.query.QuerySet`:  A query set of the Worker objects which
                are considered by Pulp to be 'dirty'.
        """
        now = timezone.now()
        age_threshold = now - timedelta(seconds=settings.WORKER_TTL)

        return self.filter(
            last_heartbeat__lt=age_threshold, cleaned_up=False, gracefully_stopped=False
        )

    def resource_managers(self):
        """
        Returns a queryset of resource managers.

        Resource managers are identified by their name. Note that some of these may be offline.

        Returns:
            :class:`django.db.models.query.QuerySet`:  A query set of the Worker objects which
                which match the resource manager name.
        """
        return self.filter(name=TASKING_CONSTANTS.RESOURCE_MANAGER_WORKER_NAME)


class Worker(BaseModel):
    """
    Represents a worker

    Fields:

        name (models.TextField): The name of the worker, in the format "worker_type@hostname"
        last_heartbeat (models.DateTimeField): A timestamp of this worker's last heartbeat
        gracefully_stopped (models.BooleanField): True if the worker has gracefully stopped. Default
            is False.
        cleaned_up (models.BooleanField): True if the worker has been cleaned up. Default is False.
    """

    objects = WorkerManager()

    name = models.TextField(db_index=True, unique=True)
    last_heartbeat = models.DateTimeField(auto_now=True)
    gracefully_stopped = models.BooleanField(default=False)
    cleaned_up = models.BooleanField(default=False)

    @property
    def online(self):
        """
        Whether a worker can be considered 'online'

        To be considered 'online', a worker must have a recent heartbeat timestamp and must not
        have the 'gracefully_stopped' flag set to True. "Recent" is defined here as "within
        the pulp process timeout interval".

        Returns:
            bool: True if the worker is considered online, otherwise False
        """
        now = timezone.now()
        age_threshold = now - timedelta(seconds=settings.WORKER_TTL)

        return not self.gracefully_stopped and self.last_heartbeat >= age_threshold

    @property
    def missing(self):
        """
        Whether a worker can be considered 'missing'

        To be considered 'missing', a worker must have a stale timestamp while also having
        gracefully_stopped=False, meaning that it was not shutdown 'cleanly' and may have died.
        Stale is defined here as "beyond the pulp process timeout interval".

        Returns:
            bool: True if the worker is considered missing, otherwise False
        """
        now = timezone.now()
        age_threshold = now - timedelta(seconds=settings.WORKER_TTL)

        return not self.gracefully_stopped and self.last_heartbeat < age_threshold

    def save_heartbeat(self):
        """
        Update the last_heartbeat field to now and save it.

        Only the last_heartbeat field will be saved. No other changes will be saved.

        Raises:
            ValueError: When the model instance has never been saved before. This method can
                only update an existing database record.
        """
        self.save(update_fields=["last_heartbeat"])


def _hash_to_u64(value):
    _digest = blake2s(value.encode(), digest_size=8).digest()
    return int.from_bytes(_digest, byteorder="big", signed=True)


class TaskManager(models.Manager):
    def filter(self, *args, **kwargs):
        value = kwargs.pop("reserved_resources_record__resource", None)
        if value is not None:
            deprecation_logger.warning(
                "Filtering tasks with 'reserved_resources_record__resource' is deprecated"
                " and may be removed as soon as pulpcore==3.15;"
                " use 'reserved_resources_record__contains' with a list of values instead."
            )
            kwargs["reserved_resources_record__contains"] = [value]
        return super().filter(*args, **kwargs)


class Task(BaseModel, AutoDeleteObjPermsMixin, AutoAddObjPermsMixin):
    """
    Represents a task

    Fields:

        state (models.TextField): The state of the task
        name (models.TextField): The name of the task
        logging_cid (models.CharField): The logging CID associated with the task
        started_at (models.DateTimeField): The time the task started executing
        finished_at (models.DateTimeField): The time the task finished executing
        error (django.contrib.postgres.fields.JSONField): Fatal errors generated by the task
        args (django.contrib.postgres.fields.JSONField): The JSON serialized arguments for the task
        kwargs (django.contrib.postgres.fields.JSONField): The JSON serialized keyword arguments for
            the task
        reserved_resources_record (django.contrib.postgres.fields.ArrayField): The reserved
            resources required for the task.

    Relations:

        parent (models.ForeignKey): Task that spawned this task (if any)
        worker (models.ForeignKey): The worker that this task is in
    """

    objects = TaskManager()

    state = models.TextField(choices=TASK_CHOICES)
    name = models.TextField()
    logging_cid = models.CharField(max_length=256, db_index=True, default="")

    started_at = models.DateTimeField(null=True)
    finished_at = models.DateTimeField(null=True)

    error = JSONField(null=True)

    args = JSONField(null=True)
    kwargs = JSONField(null=True)

    worker = models.ForeignKey("Worker", null=True, related_name="tasks", on_delete=models.SET_NULL)

    parent_task = models.ForeignKey(
        "Task", null=True, related_name="child_tasks", on_delete=models.SET_NULL
    )
    task_group = models.ForeignKey(
        "TaskGroup", null=True, related_name="tasks", on_delete=models.SET_NULL
    )
    reserved_resources_record = ArrayField(models.CharField(max_length=256), null=True)

    # TODO: find a solution that makes this unnecessary
    # The purpose of this is to enable cancelling the job scheduled on the resource manager
    # as it has a separate job ID that is not the task ID.
    _resource_job_id = models.UUIDField(null=True)

    ACCESS_POLICY_VIEWSET_NAME = "tasks"

    def __str__(self):
        return "Task: {name} [{state}]".format(name=self.name, state=self.state)

    def __enter__(self):
        self.lock = _hash_to_u64(str(self.pk))
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_try_advisory_lock(%s);", [self.lock])
            acquired = cursor.fetchone()[0]
        if not acquired:
            raise AdvisoryLockError("Could not acquire lock.")
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_unlock(%s);", [self.lock])
            released = cursor.fetchone()[0]
        if not released:
            raise RuntimeError("Lock not held.")

    @staticmethod
    def current():
        """
        Returns:
            pulpcore.app.models.Task: The current task.
        """
        try:
            if settings.USE_NEW_WORKER_TYPE:
                task_id = os.environ["PULP_TASK_ID"]
            else:
                task_id = get_current_job().id
        except (AttributeError, KeyError):
            task = None
        else:
            task = Task.objects.get(pk=task_id)
        return task

    def set_running(self):
        """
        Set this Task to the running state, save it, and log output in warning cases.

        This updates the :attr:`started_at` and sets the :attr:`state` to :attr:`RUNNING`.
        """
        rows = Task.objects.filter(pk=self.pk, state=TASK_STATES.WAITING).update(
            state=TASK_STATES.RUNNING, started_at=timezone.now()
        )
        if rows != 1:
            _logger.warning(_("Task __call__() occurred but Task %s is not at WAITING") % self.pk)
        self.refresh_from_db()

    def set_completed(self):
        """
        Set this Task to the completed state, save it, and log output in warning cases.

        This updates the :attr:`finished_at` and sets the :attr:`state` to :attr:`COMPLETED`.
        """
        # Only set the state to finished if it's not already in a complete state. This is
        # important for when the task has been canceled, so we don't move the task from canceled
        # to finished.
        rows = (
            Task.objects.filter(pk=self.pk)
            .exclude(state__in=TASK_FINAL_STATES)
            .update(state=TASK_STATES.COMPLETED, finished_at=timezone.now())
        )
        if rows != 1:
            msg = _("Task set_completed() occurred but Task %s is already in final state")
            _logger.warning(msg % self.pk)
        self.refresh_from_db()

    def set_failed(self, exc, tb):
        """
        Set this Task to the failed state and save it.

        This updates the :attr:`finished_at` attribute, sets the :attr:`state` to
        :attr:`FAILED`, and sets the :attr:`error` attribute.

        Args:
            exc (Exception): The exception raised by the task.
            tb (traceback): Traceback instance for the current exception.
        """
        tb_str = "".join(traceback.format_tb(tb))
        rows = (
            Task.objects.filter(pk=self.pk)
            .exclude(state__in=TASK_FINAL_STATES)
            .update(
                state=TASK_STATES.FAILED,
                finished_at=timezone.now(),
                error=exception_to_dict(exc, tb_str),
            )
        )
        if rows != 1:
            raise RuntimeError("Attempt to set a finished task to failed.")
        self.refresh_from_db()

    def release_resources(self):
        """
        Release the reserved resources that are reserved by this task. If a reserved resource no
        longer has any tasks reserving it, delete it.
        """
        for reserved_resource in self.reserved_resources.all():
            TaskReservedResource.objects.filter(task=self.pk).delete()
            if not reserved_resource.tasks.exists():
                with suppress(IntegrityError):
                    reserved_resource.delete()

    class Meta:
        indexes = [models.Index(fields=["pulp_created"])]


class TaskGroup(BaseModel):
    description = models.TextField()
    all_tasks_dispatched = models.BooleanField(default=False)

    @staticmethod
    def current():
        """
        Returns:
            pulpcore.app.models.TaskGroup: The task group the current task is being executed and
            belongs to.
        """
        try:
            task_group = Task.current().task_group
        except AttributeError:
            task_group = None
        return task_group

    def finish(self):
        """
        Finalize the task group.

        Set 'all_tasks_dispatched' to True so that API users can know that there are no
        tasks in the group yet to be created.
        """
        self.all_tasks_dispatched = True
        self.save()


class CreatedResource(GenericRelationModel):
    """
    Resources created by the task.

    Relations:
        task (models.ForeignKey): The task that created the resource.
    """

    task = models.ForeignKey(
        Task, related_name="created_resources", default=Task.current, on_delete=models.CASCADE
    )
