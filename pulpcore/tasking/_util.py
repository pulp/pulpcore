import asyncio
import importlib
import logging
import os
import resource
import signal
import sys
import threading
import time
from gettext import gettext as _

from django.conf import settings
from django.db import connection, transaction
from django.db.models import Q
from django.utils import timezone
from django_guid import set_guid
from django_guid.utils import generate_guid
from pulpcore.app.models import Artifact, Content, Task, TaskSchedule
from pulpcore.app.role_util import get_users_with_perms
from pulpcore.app.util import (
    set_current_user,
    set_domain,
    configure_analytics,
    configure_cleanup,
)
from pulpcore.constants import TASK_FINAL_STATES, TASK_STATES, VAR_TMP_PULP
from pulpcore.exceptions import AdvisoryLockError
from pulpcore.tasking.tasks import dispatch, execute_task

_logger = logging.getLogger(__name__)


class PGAdvisoryLock:
    """
    A context manager that will hold a postgres advisory lock non-blocking.

    The locks can be chosen from a lock group to avoid collisions. They will never collide with the
    locks used for tasks.
    """

    def __init__(self, lock, lock_group=0):
        self.lock_group = lock_group
        self.lock = lock

    def __enter__(self):
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_try_advisory_lock(%s, %s)", [self.lock_group, self.lock])
            acquired = cursor.fetchone()[0]
        if not acquired:
            raise AdvisoryLockError("Could not acquire lock.")
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_unlock(%s, %s)", [self.lock_group, self.lock])
            released = cursor.fetchone()[0]
        if not released:
            raise RuntimeError("Lock not held.")


def startup_hook():
    configure_analytics()
    configure_cleanup()


def delete_incomplete_resources(task):
    """
    Delete all incomplete created-resources on a canceled task.

    Args:
        task (Task): A task.
    """
    if task.state != TASK_STATES.CANCELING:
        raise RuntimeError(_("Task must be canceling."))
    for model in (r.content_object for r in task.created_resources.all()):
        if isinstance(model, (Artifact, Content)):
            continue
        try:
            if model.complete:
                continue
        except AttributeError:
            continue
        try:
            with transaction.atomic():
                model.delete()
        except Exception as error:
            _logger.error(_("Delete created resource, failed: {}").format(str(error)))


def write_memory_usage(path):
    _logger.info("Writing task memory data to {}".format(path))

    with open(path, "w") as file:
        file.write("# Seconds\tMemory in MB\n")
        seconds = 0
        while True:
            current_mb_in_use = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024
            file.write(f"{seconds}\t{current_mb_in_use:.2f}\n")
            file.flush()
            time.sleep(5)
            seconds += 5


def child_signal_handler(sig, frame):
    _logger.debug("Signal %s recieved by %s.", sig, os.getpid())
    # Reset signal handlers to default
    # If you kill the process a second time it's not graceful anymore.
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    signal.signal(signal.SIGTERM, signal.SIG_DFL)
    signal.signal(signal.SIGHUP, signal.SIG_DFL)
    signal.signal(signal.SIGUSR1, signal.SIG_DFL)

    if sig == signal.SIGUSR1:
        sys.exit()


def perform_task(task_pk, task_working_dir_rel_path):
    """Setup the environment to handle a task and execute it.
    This must be called as a subprocess, while the parent holds the advisory lock of the task."""
    signal.signal(signal.SIGINT, child_signal_handler)
    signal.signal(signal.SIGTERM, child_signal_handler)
    signal.signal(signal.SIGHUP, child_signal_handler)
    signal.signal(signal.SIGUSR1, child_signal_handler)
    if settings.TASK_DIAGNOSTICS:
        diagnostics_dir = VAR_TMP_PULP / str(task_pk)
        diagnostics_dir.mkdir(parents=True, exist_ok=True)
        mem_diagnostics_path = diagnostics_dir / "memory.datum"
        # It would be better to have this recording happen in the parent process instead of here
        # https://github.com/pulp/pulpcore/issues/2337
        mem_diagnostics_thread = threading.Thread(
            target=write_memory_usage, args=(mem_diagnostics_path,), daemon=True
        )
        mem_diagnostics_thread.start()
    # All processes need to create their own postgres connection
    connection.connection = None
    task = Task.objects.select_related("pulp_domain").get(pk=task_pk)
    # These queries were specifically constructed and ordered this way to ensure we have the highest
    # chance of getting the user who dispatched the task since we don't have a user relation on the
    # task model. The second query acts as a fallback to provide ZDU support. Future changes will
    # require to keep these around till a breaking change release is planned (3.70 the earliest).
    user = (
        get_users_with_perms(
            task,
            only_with_perms_in=["core.add_task"],
            with_group_users=False,
            include_model_permissions=False,
            include_domain_permissions=False,
        ).first()
        or get_users_with_perms(
            task,
            only_with_perms_in=["core.manage_roles_task"],
            with_group_users=False,
            include_model_permissions=False,
            include_domain_permissions=False,
        ).first()
    )
    # Isolate from the parent asyncio.
    asyncio.set_event_loop(asyncio.new_event_loop())
    # Set current contexts
    set_guid(task.logging_cid)
    set_current_user(user)
    set_domain(task.pulp_domain)
    os.chdir(task_working_dir_rel_path)

    # set up profiling
    if settings.TASK_DIAGNOSTICS and importlib.util.find_spec("pyinstrument") is not None:
        from pyinstrument import Profiler

        with Profiler() as profiler:
            execute_task(task)

        profile_file = diagnostics_dir / "pyinstrument.html"
        _logger.info("Writing task profile data to {}".format(profile_file))
        with open(profile_file, "w+") as f:
            f.write(profiler.output_html())
    else:
        execute_task(task)


def dispatch_scheduled_tasks():
    # Warning, dispatch_scheduled_tasks is not race condition free!
    now = timezone.now()
    # Dispatch all tasks old enough and not still running
    for task_schedule in TaskSchedule.objects.filter(next_dispatch__lte=now).filter(
        Q(last_task=None) | Q(last_task__state__in=TASK_FINAL_STATES)
    ):
        try:
            if task_schedule.dispatch_interval is None:
                # This was a timed one shot task schedule
                task_schedule.next_dispatch = None
            else:
                # This is a recurring task schedule
                while task_schedule.next_dispatch < now:
                    # Do not schedule in the past
                    task_schedule.next_dispatch += task_schedule.dispatch_interval
            set_guid(generate_guid())
            with transaction.atomic():
                task_schedule.last_task = dispatch(
                    task_schedule.task_name,
                )
                task_schedule.save(update_fields=["next_dispatch", "last_task"])

            _logger.info(
                "Dispatched scheduled task {task_name} as task id {task_id}".format(
                    task_name=task_schedule.task_name, task_id=task_schedule.last_task.pk
                )
            )
        except Exception as e:
            _logger.warning(
                "Dispatching scheduled task {task_name} failed. {error}".format(
                    task_name=task_schedule.task_name, error=str(e)
                )
            )
