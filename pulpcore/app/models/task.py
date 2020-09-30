"""
Django models related to the Tasking system
"""
import logging
import traceback
from datetime import timedelta
from gettext import gettext as _

from django.contrib.postgres.fields import JSONField
from django.db import models, transaction
from django.utils import timezone
from rq.job import get_current_job

from pulpcore.app.models import (
    AutoAddObjPermsMixin,
    AutoDeleteObjPermsMixin,
    BaseModel,
    GenericRelationModel,
)
from pulpcore.constants import TASK_CHOICES, TASK_FINAL_STATES, TASK_STATES
from pulpcore.exceptions import exception_to_dict
from pulpcore.tasking.constants import TASKING_CONSTANTS

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

    resource = models.ForeignKey("ReservedResource", on_delete=models.CASCADE)
    task = models.ForeignKey("Task", on_delete=models.PROTECT)


class ReservedResourceRecord(BaseModel):
    """
    Resources that have been reserved.

    This model is a duplicate of ReservedResource. A worker is not included in
    the model because it will prevent the tasking system to release duplicated
    reserved resources automatically.

    Fields:

        resource (models.TextField): The url of the resource reserved for the task.

    Relations:

        task (models.ForeignKey): The task associated with this reservation
    """

    resource = models.TextField(unique=True)
    tasks = models.ManyToManyField(
        "Task", related_name="reserved_resources_record", through="TaskReservedResourceRecord"
    )


class TaskReservedResourceRecord(BaseModel):
    """
    Association between a Task and its ReservedResourcesRecord.

    Prevents the task from being deleted if it has any ReservedResource(s).
    This model is a duplicate of TaskReservedResource. When the task is being
    deleted from a database, the associated TaskReservedResourceRecord will
    be deleted as well.

    Relations:

        task (models.ForeignKey): The associated task.
        resource (models.ForeignKey): The associated resource.
    """

    resource = models.ForeignKey("ReservedResourceRecord", on_delete=models.CASCADE)
    task = models.ForeignKey("Task", on_delete=models.CASCADE)


class WorkerManager(models.Manager):
    def get_unreserved_worker(self):
        """
        Randomly selects an unreserved :class:`~pulpcore.app.models.Worker`

        Return a random Worker instance that has no :class:`~pulpcore.app.models.ReservedResource`
        associated with it. If all workers have at least one ReservedResource relationship, a
        :class:`pulpcore.app.models.Worker.DoesNotExist` exception is raised.

        This method filters out resource managers which do not process end-user Tasks.

        This method provides randomization for Worker selection to distribute load across workers.

        Returns:
            :class:`pulpcore.app.models.Worker`: A randomly-selected Worker instance that has zero
                :class:`~pulpcore.app.models.ReservedResource` entries associated with it.

        Raises:
            Worker.DoesNotExist: If all Workers have at least one ReservedResource entry.
        """
        workers_qs = self.online_workers().exclude(
            name=TASKING_CONSTANTS.RESOURCE_MANAGER_WORKER_NAME
        )
        workers_qs_with_counts = workers_qs.annotate(models.Count("reservations"))
        try:
            return workers_qs_with_counts.filter(reservations__count=0).order_by("?")[0]
        except IndexError:
            raise self.model.DoesNotExist()

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
        age_threshold = now - timedelta(seconds=TASKING_CONSTANTS.WORKER_TTL)

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
        age_threshold = now - timedelta(seconds=TASKING_CONSTANTS.WORKER_TTL)

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
        age_threshold = now - timedelta(seconds=TASKING_CONSTANTS.WORKER_TTL)

        return self.filter(
            last_heartbeat__lt=age_threshold, cleaned_up=False, gracefully_stopped=False
        )

    def with_reservations(self, resources):
        """
        Returns a worker with the resources reserved.

        This worker may have ANY of the reservations for resources specified by resource urls. This
        is useful when looking for a worker to queue work against as we don't care if it doesn't
        have all the reservations as we can still try creating reservations for the additional
        resources we need.

        Arguments:
            resources (list): a list of resource urls

        Returns:
            :class:`pulpcore.app.models.Worker`: A worker with locks on resources

        Raises:
            Worker.DoesNotExist: If no worker has all resources locked
            Worker.MultipleObjectsReturned: More than one worker holds reservations
        """
        return self.filter(reservations__resource__in=resources).distinct().get()

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
        age_threshold = now - timedelta(seconds=TASKING_CONSTANTS.WORKER_TTL)

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
        age_threshold = now - timedelta(seconds=TASKING_CONSTANTS.WORKER_TTL)

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

    def lock_resources(self, task, resource_urls):
        """
        Attempt to lock all resources by their urls. Must be atomic to prevent deadlocks.

        Arguments:
            task (pulpcore.app.models.Task): task to lock the resource for
            resource_urls (List): a list of resource urls to be locked

        Raises:
            django.db.IntegrityError: If the reservation already exists
        """
        with transaction.atomic():
            for resource in resource_urls:
                if self.reservations.filter(resource=resource).exists():
                    reservation = self.reservations.get(resource=resource)
                else:
                    reservation = ReservedResource.objects.create(worker=self, resource=resource)
                TaskReservedResource.objects.create(resource=reservation, task=task)


class Task(BaseModel, AutoDeleteObjPermsMixin, AutoAddObjPermsMixin):
    """
    Represents a task

    Fields:

        state (models.TextField): The state of the task
        name (models.TextField): The name of the task
        logging_cid (models.CharField): The logging CID associated with the task
        started_at (models.DateTimeField): The time the task started executing
        finished_at (models.DateTimeField): The time the task finished executing
        error (pulpcore.app.fields.JSONField): Fatal errors generated by the task

    Relations:

        parent (models.ForeignKey): Task that spawned this task (if any)
        worker (models.ForeignKey): The worker that this task is in
    """

    state = models.TextField(choices=TASK_CHOICES)
    name = models.TextField()
    logging_cid = models.CharField(max_length=256, db_index=True, default="")

    started_at = models.DateTimeField(null=True)
    finished_at = models.DateTimeField(null=True)

    error = JSONField(null=True)
    worker = models.ForeignKey("Worker", null=True, related_name="tasks", on_delete=models.SET_NULL)

    parent_task = models.ForeignKey(
        "Task", null=True, related_name="child_tasks", on_delete=models.SET_NULL
    )
    task_group = models.ForeignKey(
        "TaskGroup", null=True, related_name="tasks", on_delete=models.SET_NULL
    )

    # TODO: find a solution that makes this unnecessary
    # The purpose of this is to enable cancelling the job scheduled on the resource manager
    # as it has a separate job ID that is not the task ID.
    _resource_job_id = models.UUIDField()

    ACCESS_POLICY_VIEWSET_NAME = "tasks"

    @staticmethod
    def current():
        """
        Returns:
            pulpcore.app.models.Task: The current task.
        """
        try:
            task_id = get_current_job().id
        except AttributeError:
            task = None
        else:
            task = Task.objects.get(pk=task_id)
        return task

    def set_running(self):
        """
        Set this Task to the running state, save it, and log output in warning cases.

        This updates the :attr:`started_at` and sets the :attr:`state` to :attr:`RUNNING`.
        """
        if self.state != TASK_STATES.WAITING:
            _logger.warning(_("Task __call__() occurred but Task %s is not at WAITING") % self.pk)
        self.state = TASK_STATES.RUNNING
        self.started_at = timezone.now()
        self.save()

    def set_completed(self):
        """
        Set this Task to the completed state, save it, and log output in warning cases.

        This updates the :attr:`finished_at` and sets the :attr:`state` to :attr:`COMPLETED`.
        """
        self.finished_at = timezone.now()

        # Only set the state to finished if it's not already in a complete state. This is
        # important for when the task has been canceled, so we don't move the task from canceled
        # to finished.
        if self.state not in TASK_FINAL_STATES:
            self.state = TASK_STATES.COMPLETED
        else:
            msg = _("Task set_completed() occurred but Task %s is already in final state")
            _logger.warning(msg % self.pk)

        self.save()

    def set_failed(self, exc, tb):
        """
        Set this Task to the failed state and save it.

        This updates the :attr:`finished_at` attribute, sets the :attr:`state` to
        :attr:`FAILED`, and sets the :attr:`error` attribute.

        Args:
            exc (Exception): The exception raised by the task.
            tb (traceback): Traceback instance for the current exception.
        """
        self.state = TASK_STATES.FAILED
        self.finished_at = timezone.now()
        tb_str = "".join(traceback.format_tb(tb))
        self.error = exception_to_dict(exc, tb_str)
        self.save()

    def release_resources(self):
        """
        Release the reserved resources that are reserved by this task. If a reserved resource no
        longer has any tasks reserving it, delete it.
        """
        for reservation in self.reserved_resources.all():
            TaskReservedResource.objects.filter(task=self.pk).delete()
            if not reservation.tasks.exists():
                reservation.delete()


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
