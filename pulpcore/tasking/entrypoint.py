import click
import logging
import os

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "pulpcore.app.settings")

django.setup()

from pulpcore.tasking.pulpcore_worker import NewPulpWorker  # noqa: E402: module level not at top


_logger = logging.getLogger(__name__)


@click.option("--pid", help="Write the process ID number to a file at the specified path")
@click.command()
def worker(pid):
    """A Pulp worker."""

    if pid:
        with open(os.path.expanduser(pid), "w") as fp:
            fp.write(str(os.getpid()))

    _logger.info("Starting distributed type worker")

    NewPulpWorker().run_forever()
