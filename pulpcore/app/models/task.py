"""
Django models related to the Tasking system
"""
import logging
import traceback
import os
from contextlib import suppress
from datetime import timedelta
from gettext import gettext as _

from django.conf import settings
from django.contrib.postgres.fields import ArrayField, HStoreField
from django.core.serializers.json import DjangoJSONEncoder
from django.db import connection, models
from django.utils import timezone

from pulpcore.app.models import (
    AutoAddObjPermsMixin,
    BaseModel,
    GenericRelationModel,
)
from pulpcore.constants import TASK_CHOICES, TASK_INCOMPLETE_STATES, TASK_STATES
from pulpcore.exceptions import AdvisoryLockError, exception_to_dict
from pulpcore.app.util import get_domain_pk

_logger = logging.getLogger(__name__)


class WorkerManager(models.Manager):
    def online_workers(self):
        """
        Returns a queryset of workers meeting the criteria to be considered 'online'

        To be considered 'online', a worker must have a recent heartbeat timestamp. "Recent" is
        defined here as "within the pulp process timeout interval".

        Returns:
            :class:`django.db.models.query.QuerySet`:  A query set of the Worker objects which
                are considered by Pulp to be 'online'.
        """
        now = timezone.now()
        age_threshold = now - timedelta(seconds=settings.WORKER_TTL)

        return self.filter(last_heartbeat__gte=age_threshold)

    def missing_workers(self, age=timedelta(seconds=settings.WORKER_TTL)):
        """
        Returns a queryset of workers meeting the criteria to be considered 'missing'

        To be considered missing, a worker must have a stale timestamp.  By default, stale is
        defined here as longer than the ``settings.WORKER_TTL``, or you can specify age as a
        timedelta.

        Args:
            age (datetime.timedelta): Workers who have heartbeats older than this time interval are
                considered missing.

        Returns:
            :class:`django.db.models.query.QuerySet`:  A query set of the Worker objects which
                are considered by Pulp to be 'missing'.
        """
        age_threshold = timezone.now() - age
        return self.filter(last_heartbeat__lt=age_threshold)


class Worker(BaseModel):
    """
    Represents a worker

    Fields:

        name (models.TextField): The name of the worker, in the format "worker_type@hostname"
        last_heartbeat (models.DateTimeField): A timestamp of this worker's last heartbeat
    """

    objects = WorkerManager()

    name = models.TextField(db_index=True, unique=True)
    last_heartbeat = models.DateTimeField(auto_now=True)
    versions = HStoreField(default=dict)

    @property
    def current_task(self):
        """
        The task this worker is currently executing, if any.

        Returns:
            Task: The currently executing task
        """
        return self.tasks.filter(state="running").first()

    @property
    def online(self):
        """
        Whether a worker can be considered 'online'

        To be considered 'online', a worker must have a recent heartbeat timestamp. "Recent" is
        defined here as "within the pulp process timeout interval".

        Returns:
            bool: True if the worker is considered online, otherwise False
        """
        now = timezone.now()
        age_threshold = now - timedelta(seconds=settings.WORKER_TTL)

        return self.last_heartbeat >= age_threshold

    @property
    def missing(self):
        """
        Whether a worker can be considered 'missing'

        To be considered 'missing', a worker must have a stale timestamp meaning that it was not
        shutdown 'cleanly' and may have died.  Stale is defined here as "beyond the pulp process
        timeout interval".

        Returns:
            bool: True if the worker is considered missing, otherwise False
        """
        now = timezone.now()
        age_threshold = now - timedelta(seconds=settings.WORKER_TTL)

        return self.last_heartbeat < age_threshold

    def save_heartbeat(self):
        """
        Update the last_heartbeat field to now and save it.

        Only the last_heartbeat field will be saved. No other changes will be saved.

        Raises:
            ValueError: When the model instance has never been saved before. This method can
                only update an existing database record.
        """
        self.save(update_fields=["last_heartbeat"])


def _uuid_to_advisory_lock(value):
    return ((value >> 64) ^ value) & 0x7FFFFFFFFFFFFFFF


class Task(BaseModel, AutoAddObjPermsMixin):
    """
    Represents a task

    Fields:

        state (models.TextField): The state of the task
        name (models.TextField): The name of the task
        logging_cid (models.TextField): The logging CID associated with the task
        started_at (models.DateTimeField): The time the task started executing
        finished_at (models.DateTimeField): The time the task finished executing
        error (models.JSONField): Fatal errors generated by the task
        args (models.JSONField): The JSON serialized arguments for the task
        kwargs (models.JSONField): The JSON serialized keyword arguments for
            the task
        reserved_resources_record (django.contrib.postgres.fields.ArrayField): The reserved
            resources required for the task.

    Relations:

        parent (models.ForeignKey): Task that spawned this task (if any)
        worker (models.ForeignKey): The worker that this task is in
        pulp_domain (models.ForeignKey): The domain the Task is a part of
    """

    state = models.TextField(choices=TASK_CHOICES)
    name = models.TextField()
    logging_cid = models.TextField(db_index=True)

    started_at = models.DateTimeField(null=True)
    finished_at = models.DateTimeField(null=True)

    error = models.JSONField(null=True)

    args = models.JSONField(null=True, encoder=DjangoJSONEncoder)
    kwargs = models.JSONField(null=True, encoder=DjangoJSONEncoder)

    worker = models.ForeignKey("Worker", null=True, related_name="tasks", on_delete=models.SET_NULL)

    parent_task = models.ForeignKey(
        "Task", null=True, related_name="child_tasks", on_delete=models.SET_NULL
    )
    task_group = models.ForeignKey(
        "TaskGroup", null=True, related_name="tasks", on_delete=models.SET_NULL
    )
    reserved_resources_record = ArrayField(models.TextField(), null=True)
    pulp_domain = models.ForeignKey("Domain", default=get_domain_pk, on_delete=models.CASCADE)

    def __str__(self):
        return "Task: {name} [{state}]".format(name=self.name, state=self.state)

    def __enter__(self):
        self.lock = _uuid_to_advisory_lock(self.pk.int)
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
            task_id = os.environ["PULP_TASK_ID"]
        except KeyError:
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
            raise RuntimeError(
                _("Task set_running() occurred but Task {} is not WAITING").format(self.pk)
            )
        with suppress(AttributeError):
            del self.state
        with suppress(AttributeError):
            del self.started_at
        with suppress(AttributeError):
            del self.finished_at
        with suppress(AttributeError):
            del self.error

    def set_completed(self):
        """
        Set this Task to the completed state, save it, and log output in warning cases.

        This updates the :attr:`finished_at` and sets the :attr:`state` to :attr:`COMPLETED`.
        """
        # Only set the state to finished if it's running. This is important for when the task has
        # been canceled, so we don't move the task from canceled to finished.
        rows = Task.objects.filter(pk=self.pk, state=TASK_STATES.RUNNING).update(
            state=TASK_STATES.COMPLETED, finished_at=timezone.now()
        )
        if rows != 1:
            raise RuntimeError(
                _("Task set_completed() occurred but Task {} is not RUNNING.").format(self.pk)
            )
        with suppress(AttributeError):
            del self.state
        with suppress(AttributeError):
            del self.started_at
        with suppress(AttributeError):
            del self.finished_at
        with suppress(AttributeError):
            del self.error

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
        rows = Task.objects.filter(pk=self.pk, state=TASK_STATES.RUNNING).update(
            state=TASK_STATES.FAILED,
            finished_at=timezone.now(),
            error=exception_to_dict(exc, tb_str),
        )
        if rows != 1:
            raise RuntimeError(_("Attempt to set a not running task to failed."))
        with suppress(AttributeError):
            del self.state
        with suppress(AttributeError):
            del self.started_at
        with suppress(AttributeError):
            del self.finished_at
        with suppress(AttributeError):
            del self.error

    def set_canceling(self):
        """
        Set this task to canceling from either waiting, running or canceling.

        This is the only valid transition without holding the task lock.
        """
        rows = Task.objects.filter(pk=self.pk, state__in=TASK_INCOMPLETE_STATES).update(
            state=TASK_STATES.CANCELING,
        )
        if rows != 1:
            raise RuntimeError(_("Attempt to cancel a finished task."))
        with suppress(AttributeError):
            del self.state
        with suppress(AttributeError):
            del self.started_at
        with suppress(AttributeError):
            del self.finished_at
        with suppress(AttributeError):
            del self.error

    def set_canceled(self, final_state=TASK_STATES.CANCELED, reason=None):
        """
        Set this task to canceled or failed from canceling.
        """
        # Make sure this function was called with a proper final state
        assert final_state in [TASK_STATES.CANCELED, TASK_STATES.FAILED]
        task_data = {}
        if reason:
            task_data["error"] = {"reason": reason}
        rows = Task.objects.filter(pk=self.pk, state=TASK_STATES.CANCELING).update(
            state=final_state,
            finished_at=timezone.now(),
            **task_data,
        )
        if rows != 1:
            raise RuntimeError(_("Attempt to mark a task canceled that is not in canceling state."))
        with suppress(AttributeError):
            del self.state
        with suppress(AttributeError):
            del self.started_at
        with suppress(AttributeError):
            del self.finished_at
        with suppress(AttributeError):
            del self.error

    # Example taken from here:
    # https://docs.djangoproject.com/en/3.2/ref/models/instances/#refreshing-objects-from-database
    def refresh_from_db(self, using=None, fields=None, **kwargs):
        # fields contains the name of the deferred field to be
        # loaded.
        if fields is not None:
            fields = set(fields)
            deferred_fields = self.get_deferred_fields()
            # If any deferred field is going to be loaded
            if fields.intersection(deferred_fields):
                # then load all of them
                fields = fields.union(deferred_fields)
        super().refresh_from_db(using, fields, **kwargs)

    class Meta:
        indexes = [models.Index(fields=["pulp_created"])]
        permissions = [
            ("manage_roles_task", "Can manage role assignments on task"),
        ]


class TaskGroup(BaseModel):
    description = models.TextField()
    all_tasks_dispatched = models.BooleanField(default=False)
    pulp_domain = models.ForeignKey("Domain", default=get_domain_pk, on_delete=models.CASCADE)

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


class TaskSchedule(BaseModel):
    name = models.TextField(unique=True, null=False)
    next_dispatch = models.DateTimeField(default=timezone.now, null=True)
    dispatch_interval = models.DurationField(null=True)
    task_name = models.TextField()
    last_task = models.ForeignKey(Task, null=True, on_delete=models.SET_NULL)

    class Meta:
        permissions = [
            ("manage_roles_taskschedule", "Can manage role assignments on task schedules"),
        ]
