import click
import logging
import os
import select
import sys

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "pulpcore.app.settings")
# Until Django supports async ORM natively this is the best we can do given these parts of Pulp
# run in coroutines. We try to ensure it is safe by never passing ORM data between co-routines.
os.environ.setdefault("DJANGO_ALLOW_ASYNC_UNSAFE", "true")

django.setup()

from django.conf import settings  # noqa: E402: module level not at top of file


_logger = logging.getLogger(__name__)


@click.option(
    "--resource-manager",
    is_flag=True,
    help="Whether this worker should be started as a resource-manager",
)
@click.option("--pid", help="Write the process ID number to a file at the specified path")
@click.command()
def worker(resource_manager, pid):
    """A Pulp worker."""

    if pid:
        with open(os.path.expanduser(pid), "w") as fp:
            fp.write(str(os.getpid()))

    if settings.USE_NEW_WORKER_TYPE:
        if resource_manager:
            _logger.warn(
                "Attempting to start a resource-manager with the distributed tasking system"
            )
            select.select([], [], [])
        _logger.info("Starting distributed type worker")
        from pulpcore.tasking.pulpcore_worker import NewPulpWorker

        NewPulpWorker().run_forever()
    else:
        _logger.info("Starting rq type worker")
        from rq.cli import main

        args = [
            "rq",
            "worker",
            "-w",
            "pulpcore.tasking.worker.PulpWorker",
            "-c",
            "pulpcore.rqconfig",
            "--disable-job-desc-logging",
        ]
        if resource_manager:
            args.extend(["-n", "resource-manager"])
        sys.argv = args
        main()
