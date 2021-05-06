import click
import logging
import os
import sys

from rq.cli import main

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

    _logger.info("Starting rq type worker")
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
