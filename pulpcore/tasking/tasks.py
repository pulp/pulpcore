import json
import logging
import time
import uuid
from gettext import gettext as _

from django.conf import settings
from django.db import IntegrityError, transaction, models, connection as db_connection
from django.db.models import Model
from django_guid.middleware import GuidMiddleware
from redis.exceptions import ConnectionError as RedisConnectionError
from rq import Queue
from rq.job import Job, get_current_job

from pulpcore.app.loggers import deprecation_logger
from pulpcore.app.models import (
    ReservedResource,
    Task,
    TaskReservedResource,
    Worker,
)
from pulpcore.constants import TASK_STATES
from pulpcore.tasking import connection, constants, util

_logger = logging.getLogger(__name__)


TASK_TIMEOUT = -1  # -1 for infinite timeout


def _acquire_worker(resources):
    """
    Attempts to acquire a worker for a set of resource urls. If no worker has any of those
    resources reserved, then the first available worker is returned.

    Must be done in a transaction, and locks the worker in question until the end of the
    transaction.

    Arguments:
        resources (list): a list of resource urls

    Returns:
        :class:`pulpcore.app.models.Worker`: A worker to queue work for

    Raises:
        Worker.DoesNotExist: If no worker is found
    """
    # Find a worker who already has one of the reservations, it is safe to send this work to them
    try:
        return (
            Worker.objects.select_for_update()
            .filter(pk__in=Worker.objects.filter(reservations__resource__in=resources))
            .get()
        )
    except Worker.MultipleObjectsReturned:
        raise Worker.DoesNotExist
    except Worker.DoesNotExist:
        pass

    # Otherwise, return any available worker at random
    workers_qs = Worker.objects.online_workers().exclude(
        name=constants.TASKING_CONSTANTS.RESOURCE_MANAGER_WORKER_NAME
    )
    workers_without_res = workers_qs.annotate(models.Count("reservations")).filter(
        reservations__count=0
    )
    # A randomly-selected Worker instance that has zero ReservedResource entries.
    worker = (
        Worker.objects.select_for_update().filter(pk__in=workers_without_res).order_by("?").first()
    )

    if worker is None:
        # If all Workers have at least one ReservedResource entry.
        raise Worker.DoesNotExist()

    return worker


def _queue_reserved_task(func, inner_task_id, resources, inner_args, inner_kwargs, options):
    """
    A task that encapsulates another task to be dispatched later.

    This task being encapsulated is called the "inner" task, and a task name, UUID, and accepts a
    list of positional args and keyword args for the inner task. These arguments are named
    inner_args and inner_kwargs. inner_args is a list, and inner_kwargs is a dictionary passed to
    the inner task as positional and keyword arguments using the * and ** operators.

    The inner task is dispatched into a dedicated queue for a worker that is decided at dispatch
    time. The logic deciding which queue receives a task is controlled through the
    find_worker function.

    Args:
        func (basestring): The function to be called
        inner_task_id (basestring): The task_id to be set on the task being called. By providing
            the UUID, the caller can have an asynchronous reference to the inner task
            that will be dispatched.
        resources (basestring): The urls of the resource you wish to reserve for your task.
            The system will ensure that no other tasks that want that same reservation will run
            concurrently with yours.
        inner_args (tuple): The positional arguments to pass on to the task.
        inner_kwargs (dict): The keyword arguments to pass on to the task.
        options (dict): For all options accepted by enqueue see the RQ docs
    """
    redis_conn = connection.get_redis_connection()
    task_status = Task.objects.get(pk=inner_task_id)
    GuidMiddleware.set_guid(task_status.logging_cid)
    task_name = func.__module__ + "." + func.__name__

    while True:
        if task_name == "pulpcore.app.tasks.orphan.orphan_cleanup":
            if ReservedResource.objects.exists():
                # wait until there are no reservations
                time.sleep(0.25)
                continue
            else:
                rq_worker = util.get_current_worker()
                worker = Worker.objects.get(name=rq_worker.name)
                task_status.worker = worker
                task_status.set_running()
                q = Queue("resource-manager", connection=redis_conn, is_async=False)
                try:
                    q.enqueue(
                        func,
                        args=inner_args,
                        kwargs=inner_kwargs,
                        job_id=inner_task_id,
                        job_timeout=TASK_TIMEOUT,
                        **options,
                    )
                    task_status.set_completed()
                except RedisConnectionError as e:
                    task_status.set_failed(e, None)
                return

        try:
            with transaction.atomic():
                # lock the worker - there is a similar lock in mark_worker_offline()
                worker = _acquire_worker(resources)

                # Attempt to lock all resources by their urls. Must be atomic to prevent deadlocks.
                for resource in resources:
                    if worker.reservations.select_for_update().filter(resource=resource).exists():
                        reservation = worker.reservations.get(resource=resource)
                    else:
                        reservation = ReservedResource.objects.create(
                            worker=worker, resource=resource
                        )
                    TaskReservedResource.objects.create(resource=reservation, task=task_status)
        except (Worker.DoesNotExist, IntegrityError):
            # if worker is ready, or we have a worker but we can't create the reservations, wait
            time.sleep(0.25)
        else:
            # we have a worker with the locks
            break

    task_status.worker = worker
    task_status.save()

    try:
        q = Queue(worker.name, connection=redis_conn)
        q.enqueue(
            func,
            args=inner_args,
            kwargs=inner_kwargs,
            job_id=inner_task_id,
            job_timeout=TASK_TIMEOUT,
            **options,
        )
    except RedisConnectionError as e:
        task_status.set_failed(e, None)


class UUIDEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, uuid.UUID):
            return str(obj)
        deprecation_logger.warning(
            _(
                "The argument {obj} is of type {type}, which is not JSON serializable. The use "
                "of non JSON serializable objects for `args` and `kwargs` to tasks is "
                "deprecated as of pulpcore==3.12."
            ).format(obj=obj, type=type(obj))
        )
        if settings.USE_NEW_WORKER_TYPE:
            return super().default(obj)
        else:
            return None


def _validate_and_get_resources(resources):
    resource_set = set()
    for r in resources:
        if isinstance(r, str):
            resource_set.add(r)
        elif isinstance(r, Model):
            resource_set.add(util.get_url(r))
        else:
            raise ValueError(_("Must be (str|Model)"))
    return list(resource_set)


def _enqueue_with_reservation(
    func, resources, args=None, kwargs=None, options=None, task_group=None
):
    if not args:
        args = tuple()
    if not kwargs:
        kwargs = dict()
    if not options:
        options = dict()

    resources = _validate_and_get_resources(resources)
    inner_task_id = str(uuid.uuid4())
    resource_task_id = str(uuid.uuid4())
    args_as_json = json.dumps(args, cls=UUIDEncoder)
    kwargs_as_json = json.dumps(kwargs, cls=UUIDEncoder)
    redis_conn = connection.get_redis_connection()
    current_job = get_current_job(connection=redis_conn)
    parent_kwarg = {}
    if current_job:
        # set the parent task of the spawned task to the current task ID (same as rq Job ID)
        parent_kwarg["parent_task"] = Task.objects.get(pk=current_job.id)

    with transaction.atomic():
        task = Task.objects.create(
            pk=inner_task_id,
            _resource_job_id=resource_task_id,
            state=TASK_STATES.WAITING,
            logging_cid=(GuidMiddleware.get_guid() or ""),
            task_group=task_group,
            name=f"{func.__module__}.{func.__name__}",
            args=args_as_json,
            kwargs=kwargs_as_json,
            reserved_resources_record=resources,
            **parent_kwarg,
        )

        task_args = (func, inner_task_id, resources, args, kwargs, options)
        try:
            q = Queue("resource-manager", connection=redis_conn)
            q.enqueue(
                _queue_reserved_task,
                job_id=resource_task_id,
                args=task_args,
                job_timeout=TASK_TIMEOUT,
            )
        except RedisConnectionError as e:
            task.set_failed(e, None)

    return Job(id=inner_task_id, connection=redis_conn)


def dispatch(func, resources, args=None, kwargs=None, task_group=None):
    """
    Enqueue a message to Pulp workers with a reservation.

    This method provides normal enqueue functionality, while also requesting necessary locks for
    serialized urls. No two tasks that claim the same resource can execute concurrently. It
    accepts resources which it transforms into a list of urls (one for each resource).

    This method creates a :class:`pulpcore.app.models.Task` object and returns it.

    The values in `args` and `kwargs` must be JSON serializable, but may contain instances of
    ``uuid.UUID``.

    Args:
        func (callable): The function to be run by RQ when the necessary locks are acquired.
        resources (list): A list of resources to this task needs exclusive access to while running.
                          Each resource can be either a `str` or a `django.models.Model` instance.
        args (tuple): The positional arguments to pass on to the task.
        kwargs (dict): The keyword arguments to pass on to the task.
        task_group (pulpcore.app.models.TaskGroup): A TaskGroup to add the created Task to.

    Returns (pulpcore.app.models.Task): The Pulp Task that was created.

    Raises:
        ValueError: When `resources` is an unsupported type.
    """
    if settings.USE_NEW_WORKER_TYPE:
        args_as_json = json.dumps(args, cls=UUIDEncoder)
        kwargs_as_json = json.dumps(kwargs, cls=UUIDEncoder)
        resources = _validate_and_get_resources(resources)
        with transaction.atomic():
            task = Task.objects.create(
                state=TASK_STATES.WAITING,
                logging_cid=(GuidMiddleware.get_guid() or ""),
                task_group=task_group,
                name=f"{func.__module__}.{func.__name__}",
                args=args_as_json,
                kwargs=kwargs_as_json,
                parent_task=Task.current(),
                reserved_resources_record=resources,
            )
        # Notify workers
        with db_connection.connection.cursor() as cursor:
            cursor.execute("NOTIFY pulp_worker_wakeup")
        return task
    else:
        RQ_job_id = _enqueue_with_reservation(
            func, resources=resources, args=args, kwargs=kwargs, task_group=task_group
        )
        return Task.objects.get(pk=RQ_job_id.id)
