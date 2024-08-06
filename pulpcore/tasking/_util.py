import asyncio
import importlib
import logging
import os
import resource
import signal
import sys
import threading
import time
import tempfile
from gettext import gettext as _

from contextlib import suppress

from django.conf import settings
from django.db import connection, transaction, IntegrityError
from django.db.models import Q
from django.utils import timezone
from django_guid import set_guid
from django_guid.utils import generate_guid
from pulpcore.app.models import Artifact, Content, Task, TaskSchedule, ProfileArtifact
from pulpcore.app.role_util import get_users_with_perms
from pulpcore.app.util import (
    set_current_user,
    set_domain,
    configure_analytics,
    configure_cleanup,
)
from pulpcore.constants import TASK_FINAL_STATES, TASK_STATES
from pulpcore.tasking.tasks import dispatch, execute_task

_logger = logging.getLogger(__name__)


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


def write_memory_usage(stop_event, path):
    with open(path, "w") as file:
        file.write("# Seconds\tMemory in MB\n")
        seconds = 0
        while not stop_event.is_set():
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
    # All processes need to create their own postgres connection
    connection.connection = None
    # enc_args and enc_kwargs are deferred by default but we actually want them
    task = Task.objects.defer(None).select_related("pulp_domain").get(pk=task_pk)
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

    if settings.TASK_DIAGNOSTICS:
        _execute_task_and_profile(task)
    else:
        execute_task(task)


def _execute_task_and_profile(task):
    with tempfile.TemporaryDirectory(dir=settings.WORKING_DIRECTORY) as temp_dir:
        pyinstrument_func = _pyinstrument_diagnostic_decorator(temp_dir, execute_task)
        memory_func = _memory_diagnostic_decorator(temp_dir, pyinstrument_func)

        memory_func(task)


def _memory_diagnostic_decorator(temp_dir, func):
    def __memory_diagnostic_decorator(task):
        mem_diagnostics_file_path = os.path.join(temp_dir, "memory.datum")
        # It would be better to have this recording happen in the parent process instead of here
        # https://github.com/pulp/pulpcore/issues/2337
        stop_event = threading.Event()
        mem_diagnostics_thread = threading.Thread(
            target=write_memory_usage, args=(stop_event, mem_diagnostics_file_path), daemon=True
        )
        mem_diagnostics_thread.start()

        func(task)

        stop_event.set()
        artifact = Artifact.init_and_validate(mem_diagnostics_file_path)
        with suppress(IntegrityError):
            artifact.save()

        ProfileArtifact.objects.get_or_create(artifact=artifact, name="memory_profile", task=task)

        _logger.info("Created memory diagnostic data.")

    return __memory_diagnostic_decorator


def _pyinstrument_diagnostic_decorator(temp_dir, func):
    def __pyinstrument_diagnostic_decorator(task):
        if importlib.util.find_spec("pyinstrument") is not None:
            from pyinstrument import Profiler

            with Profiler() as profiler:
                func(task)

            profile_file_path = os.path.join(temp_dir, "pyinstrument.html")
            with open(profile_file_path, "w+") as f:
                f.write(profiler.output_html())
                f.flush()

            artifact = Artifact.init_and_validate(str(profile_file_path))
            with suppress(IntegrityError):
                artifact.save()

            ProfileArtifact.objects.get_or_create(
                artifact=artifact, name="pyinstrument_data", task=task
            )

            _logger.info("Created pyinstrument profile data.")
        else:
            func(task)

    return __pyinstrument_diagnostic_decorator


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
