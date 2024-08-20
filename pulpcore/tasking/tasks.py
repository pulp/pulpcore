import asyncio
import contextlib
import contextvars
import importlib
import logging
import sys
import traceback
from datetime import timedelta
from gettext import gettext as _

# NOTE: in spite of the name, cloudevents.http.CloudEvent is appropriate for other protocols
from cloudevents.http import CloudEvent
from cloudevents.kafka import to_structured
from django.conf import settings
from django.db import connection, transaction
from django.db.models import Model, Max
from django_guid import get_guid
from pulpcore.app.apps import MODULE_PLUGIN_VERSIONS
from pulpcore.app.models import Task, TaskGroup
from pulpcore.app.serializers.task import TaskStatusMessageSerializer
from pulpcore.app.util import current_task, get_domain, get_prn
from pulpcore.constants import (
    TASK_FINAL_STATES,
    TASK_INCOMPLETE_STATES,
    TASK_STATES,
    TASK_DISPATCH_LOCK,
)
from pulpcore.tasking.kafka import get_kafka_producer

_logger = logging.getLogger(__name__)

_kafka_tasks_status_topic = settings.get("KAFKA_TASKS_STATUS_TOPIC")
_kafka_tasks_status_producer_sync_enabled = settings.get("KAFKA_TASKS_STATUS_PRODUCER_SYNC_ENABLED")


def _validate_and_get_resources(resources):
    resource_set = set()
    for r in resources:
        if isinstance(r, str):
            resource_set.add(r)
        elif isinstance(r, Model):
            resource_set.add(get_prn(r))
        elif r is None:
            # Silently drop None values
            pass
        else:
            raise ValueError(_("Must be (str|Model)"))
    return list(resource_set)


def wakeup_worker():
    # Notify workers
    with connection.connection.cursor() as cursor:
        cursor.execute("NOTIFY pulp_worker_wakeup")


def execute_task(task):
    # This extra stack is needed to isolate the current_task ContextVar
    contextvars.copy_context().run(_execute_task, task)


def _execute_task(task):
    # Store the task id in the context for `Task.current()`.
    current_task.set(task)
    task.set_running()
    domain = get_domain()
    try:
        _logger.info(_("Starting task %s in domain: %s"), task.pk, domain.name)

        # Execute task
        module_name, function_name = task.name.rsplit(".", 1)
        module = importlib.import_module(module_name)
        func = getattr(module, function_name)
        args = task.enc_args or ()
        kwargs = task.enc_kwargs or {}
        result = func(*args, **kwargs)
        if asyncio.iscoroutine(result):
            _logger.debug(_("Task is coroutine %s"), task.pk)
            loop = asyncio.get_event_loop()
            loop.run_until_complete(result)

    except Exception:
        exc_type, exc, tb = sys.exc_info()
        task.set_failed(exc, tb)
        _logger.info(_("Task %s failed (%s) in domain: %s"), task.pk, exc, domain.name)
        _logger.info("\n".join(traceback.format_list(traceback.extract_tb(tb))))
        _send_task_notification(task)
    else:
        task.set_completed()
        _logger.info(_("Task completed %s in domain: %s"), task.pk, domain.name)
        _send_task_notification(task)


def dispatch(
    func,
    args=None,
    kwargs=None,
    task_group=None,
    exclusive_resources=None,
    shared_resources=None,
    immediate=False,
    deferred=True,
    versions=None,
):
    """
    Enqueue a message to Pulp workers with a reservation.

    This method provides normal enqueue functionality, while also requesting necessary locks for
    serialized urls. No two tasks that claim the same resource can execute concurrently. It
    accepts resources which it transforms into a list of urls (one for each resource).

    This method creates a [pulpcore.app.models.Task][] object and returns it.

    The values in `args` and `kwargs` must be JSON serializable, but may contain instances of
    ``uuid.UUID``.

    Args:
        func (callable | str): The function to be run when the necessary locks are acquired.
        args (tuple): The positional arguments to pass on to the task.
        kwargs (dict): The keyword arguments to pass on to the task.
        task_group (pulpcore.app.models.TaskGroup): A TaskGroup to add the created Task to.
        exclusive_resources (list): A list of resources this task needs exclusive access to while
            running. Each resource can be either a `str` or a `django.models.Model` instance.
        shared_resources (list): A list of resources this task needs non-exclusive access to while
            running. Each resource can be either a `str` or a `django.models.Model` instance.
        immediate (bool): Whether to allow running this task immediately. It must be guaranteed to
            execute fast without blocking. If not all resource constraints are met, the task will
            either be returned in a canceled state or, if `deferred` is `True` be left in the queue
            to be picked up by a worker eventually. Defaults to `False`.
        deferred (bool): Whether to allow defer running the task to a pulpcore_worker. Defaults to
            `True`. `immediate` and `deferred` cannot both be `False`.
        versions (Optional[Dict[str, str]]): Minimum versions of components by app_label the worker
            must provide to handle the task.

    Returns (pulpcore.app.models.Task): The Pulp Task that was created.

    Raises:
        ValueError: When `resources` is an unsupported type.
    """

    assert deferred or immediate, "A task must be at least `deferred` or `immediate`."

    if callable(func):
        function_name = f"{func.__module__}.{func.__name__}"
    else:
        function_name = func

    if versions is None:
        versions = MODULE_PLUGIN_VERSIONS[function_name.split(".", maxsplit=1)[0]]

    if exclusive_resources is None:
        exclusive_resources = []
    else:
        exclusive_resources = _validate_and_get_resources(exclusive_resources)
    if shared_resources is None:
        shared_resources = []
    else:
        shared_resources = _validate_and_get_resources(shared_resources)

    # A task that is exclusive on a domain will block all tasks within that domain
    domain_prn = get_prn(get_domain())
    if domain_prn not in exclusive_resources:
        shared_resources.append(domain_prn)
    resources = exclusive_resources + [f"shared:{resource}" for resource in shared_resources]

    notify_workers = False
    with contextlib.ExitStack() as stack:
        with transaction.atomic():
            # Task creation need to be serialized so that pulp_created will provide a stable order
            # at every time. We specifically need to ensure that each task, when commited to the
            # task table will be the newest with respect to `pulp_created`.
            with connection.cursor() as cursor:
                # Wait for exclusive access and release automatically after transaction.
                cursor.execute("SELECT pg_advisory_xact_lock(%s, %s)", [0, TASK_DISPATCH_LOCK])
            newest_created = Task.objects.aggregate(Max("pulp_created"))["pulp_created__max"]
            task = Task.objects.create(
                state=TASK_STATES.WAITING,
                logging_cid=(get_guid()),
                task_group=task_group,
                name=function_name,
                enc_args=args,
                enc_kwargs=kwargs,
                parent_task=Task.current(),
                reserved_resources_record=resources,
                versions=versions,
            )
            if newest_created and task.pulp_created <= newest_created:
                # Let this workaround not row forever into the future.
                if newest_created - task.pulp_created > timedelta(seconds=1):
                    # Do not commit the transaction if this condition is not met.
                    # If we ever hit this, think about delegating the timestamping to PostgresQL.
                    raise RuntimeError("Clockscrew detected. Task dispatching would be dangerous.")
                # Try to work around the smaller glitch
                task.pulp_created = newest_created + timedelta(milliseconds=1)
                task.save()
            if task_group:
                task_group.refresh_from_db()
                if task_group.all_tasks_dispatched:
                    task.set_canceling()
                    task.set_canceled(
                        TASK_STATES.CANCELED, "All tasks in group have been dispatched/canceled."
                    )
                    return task
            if immediate:
                # Grab the advisory lock before the task hits the db.
                stack.enter_context(task)
            else:
                notify_workers = True
        if immediate:
            prior_tasks = Task.objects.filter(
                state__in=TASK_INCOMPLETE_STATES, pulp_created__lt=task.pulp_created
            )
            # Compile a list of resources that must not be taken by other tasks.
            colliding_resources = (
                shared_resources
                + exclusive_resources
                + [f"shared:{resource}" for resource in exclusive_resources]
            )
            # Can we execute this task immediately?
            if (
                not colliding_resources
                or not prior_tasks.filter(
                    reserved_resources_record__overlap=colliding_resources
                ).exists()
            ):
                task.unblock()
                execute_task(task)
                if resources:
                    notify_workers = True
            elif deferred:
                notify_workers = True
            else:
                task.set_canceling()
                task.set_canceled(TASK_STATES.CANCELED, "Resources temporarily unavailable.")
    if notify_workers:
        wakeup_worker()
    return task


def cancel_task(task_id):
    """
    Cancel the task that is represented by the given task_id.

    This method cancels only the task with given task_id, not the spawned tasks. This also updates
    task's state to 'canceling'.

    Args:
        task_id (str): The ID of the task you wish to cancel

    Raises:
        rest_framework.exceptions.NotFound: If a task with given task_id does not exist
    """
    task = Task.objects.select_related("pulp_domain").get(pk=task_id)

    if task.state in TASK_FINAL_STATES:
        # If the task is already done, just stop
        _logger.debug(
            "Task [{task_id}] in domain: {name} already in a final state: {state}".format(
                task_id=task_id, name=task.pulp_domain.name, state=task.state
            )
        )
        return task
    _logger.info(
        _("Canceling task: {id} in domain: {name}").format(id=task_id, name=task.pulp_domain.name)
    )

    # This is the only valid transition without holding the task lock
    task.set_canceling()
    # Notify the worker that might be running that task and other workers to clean up
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_notify('pulp_worker_cancel', %s)", (str(task.pk),))
        cursor.execute("NOTIFY pulp_worker_wakeup")
    return task


def cancel_task_group(task_group_id):
    """
    Cancel the task group that is represented by the given task_group_id.

    This method attempts to cancel all tasks in the task group.

    Args:
        task_group_id (str): The ID of the task group you wish to cancel

    Raises:
        TaskGroup.DoesNotExist: If a task group with given task_group_id does not exist
    """
    task_group = TaskGroup.objects.get(pk=task_group_id)
    task_group.all_tasks_dispatched = True
    task_group.save(update_fields=["all_tasks_dispatched"])

    TASK_RUNNING_STATES = (TASK_STATES.RUNNING, TASK_STATES.WAITING)
    tasks = task_group.tasks.filter(state__in=TASK_RUNNING_STATES).values_list("pk", flat=True)
    for task_id in tasks:
        try:
            cancel_task(task_id)
        except RuntimeError:
            pass
    return task_group


def _send_task_notification(task):
    kafka_producer = get_kafka_producer()
    if kafka_producer is not None:
        attributes = {
            "type": "pulpcore.tasking.status",
            "source": "pulpcore.tasking",
            "datacontenttype": "application/json",
            "dataref": "https://github.com/pulp/pulpcore/blob/main/docs/static/task-status-v1.yaml",
        }
        data = TaskStatusMessageSerializer(task, context={"request": None}).data
        task_message = to_structured(CloudEvent(attributes, data))
        kafka_producer.produce(
            topic=_kafka_tasks_status_topic,
            value=task_message.value,
            key=task_message.key,
            headers=task_message.headers,
            on_delivery=_report_message_delivery,
        )
        if _kafka_tasks_status_producer_sync_enabled:
            kafka_producer.flush()


def _report_message_delivery(error, message):
    if error is not None:
        _logger.error(error)
    elif _logger.isEnabledFor(logging.DEBUG):
        _logger.debug(f"Message delivery successfully with contents {message.value}")
