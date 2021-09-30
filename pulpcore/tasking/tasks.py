import json
import logging
import uuid
from gettext import gettext as _

from django.db import transaction, connection
from django.db.models import Model
from django_guid import get_guid

from pulpcore.app.models import Task
from pulpcore.constants import TASK_STATES
from pulpcore.tasking import util

_logger = logging.getLogger(__name__)


TASK_TIMEOUT = -1  # -1 for infinite timeout


class UUIDEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, uuid.UUID):
            return str(obj)
        return super().default(obj)


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


def dispatch(
    func,
    args=None,
    kwargs=None,
    task_group=None,
    exclusive_resources=None,
    shared_resources=None,
):
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
        args (tuple): The positional arguments to pass on to the task.
        kwargs (dict): The keyword arguments to pass on to the task.
        task_group (pulpcore.app.models.TaskGroup): A TaskGroup to add the created Task to.
        exclusive_resources (list): A list of resources this task needs exclusive access to while
            running. Each resource can be either a `str` or a `django.models.Model` instance.
        shared_resources (list): A list of resources this task needs non-exclusive access to while
            running. Each resource can be either a `str` or a `django.models.Model` instance.

    Returns (pulpcore.app.models.Task): The Pulp Task that was created.

    Raises:
        ValueError: When `resources` is an unsupported type.
    """

    if exclusive_resources is None:
        exclusive_resources = []

    args_as_json = json.dumps(args, cls=UUIDEncoder)
    kwargs_as_json = json.dumps(kwargs, cls=UUIDEncoder)
    resources = _validate_and_get_resources(exclusive_resources)
    if shared_resources:
        resources.extend(
            (f"shared:{resource}" for resource in _validate_and_get_resources(shared_resources))
        )
    with transaction.atomic():
        task = Task.objects.create(
            state=TASK_STATES.WAITING,
            logging_cid=(get_guid() or ""),
            task_group=task_group,
            name=f"{func.__module__}.{func.__name__}",
            args=args_as_json,
            kwargs=kwargs_as_json,
            parent_task=Task.current(),
            reserved_resources_record=resources,
        )
    # Notify workers
    with connection.connection.cursor() as cursor:
        cursor.execute("NOTIFY pulp_worker_wakeup")
    return task
