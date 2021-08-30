import click
import logging
import os
import select

import django

from pulpcore.app.loggers import deprecation_logger

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "pulpcore.app.settings")
# Until Django supports async ORM natively this is the best we can do given these parts of Pulp
# run in coroutines. We try to ensure it is safe by never passing ORM data between co-routines.
os.environ.setdefault("DJANGO_ALLOW_ASYNC_UNSAFE", "true")

django.setup()

from pulpcore.tasking.pulpcore_worker import NewPulpWorker  # noqa: E402: module level not at top


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

    if resource_manager:
        _logger.warn("Attempting to start a resource-manager with the distributed tasking system")
        deprecation_logger.warn(
            "The `--resource-manager` option of the pulpcore-worker entrypoint is deprecated and"
            " will be removed in pulpcore 3.17."
        )
        select.select([], [], [])
    _logger.info("Starting distributed type worker")

    NewPulpWorker().run_forever()
