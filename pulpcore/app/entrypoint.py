from contextvars import ContextVar
from logging import getLogger
import os
import sys

import click
import django
from django.db import connection
from django.db.utils import IntegrityError, InterfaceError, DatabaseError
from gunicorn.arbiter import Arbiter
from gunicorn.workers.sync import SyncWorker

from pulpcore.app.apps import pulp_plugin_configs
from pulpcore.app.netutil import has_ipv6
from pulpcore.app.pulpcore_gunicorn_application import PulpcoreGunicornApplication

logger = getLogger(__name__)


name_template_var = ContextVar("name_template_var", default=None)
using_pulp_api_worker = ContextVar("using_pulp_api_worker", default=False)


class PulpApiWorker(SyncWorker):
    def notify(self):
        super().notify()
        self.heartbeat()

    def heartbeat(self):
        try:
            self.app_status.save_heartbeat()
            logger.debug(self.beat_msg)
        except (InterfaceError, DatabaseError):
            connection.close_if_unusable_or_obsolete()
            try:
                self.app_status.save_heartbeat()
                logger.debug(self.beat_msg)
            except (InterfaceError, DatabaseError):
                logger.error(self.fail_beat_msg)
                exit(Arbiter.WORKER_BOOT_ERROR)

    def init_process(self):
        os.environ.setdefault("DJANGO_SETTINGS_MODULE", "pulpcore.app.settings")
        django.setup()

        from django.conf import settings
        from pulpcore.app.models import AppStatus
        from pulpcore.app.util import get_worker_name

        name_template = name_template_var.get()
        if name_template:
            settings.set("WORKER_NAME_TEMPLATE", name_template)
        if settings.API_APP_TTL < 2 * self.timeout:
            logger.warning(
                "API_APP_TTL (%s) is smaller than double the gunicorn timeout (%s). "
                "You may experience workers wrongly reporting as missing",
                settings.API_APP_TTL,
                self.timeout,
            )

        self.name = get_worker_name()
        self.versions = {app.label: app.version for app in pulp_plugin_configs()}
        self.beat_msg = (
            "Api App '{name}' heartbeat written, sleeping for '{interarrival}' seconds".format(
                name=self.name, interarrival=self.timeout
            )
        )
        self.fail_beat_msg = (
            "Api App '{name}' failed to write a heartbeat to the database."
        ).format(name=self.name)
        try:
            self.app_status = AppStatus.objects.create(
                name=self.name, app_type="api", versions=self.versions
            )
        except IntegrityError:
            logger.error(f"An API app with name {self.name} already exists in the database.")
            exit(Arbiter.WORKER_BOOT_ERROR)

        super().init_process()

    def run(self):
        try:
            super().run()
        finally:
            # cleanup
            if self.app_status:
                self.app_status.delete()


class PulpcoreApiApplication(PulpcoreGunicornApplication):
    def load_app_specific_config(self):
        self.set_option("default_proc_name", "pulpcore-api", enforced=True)
        self.set_option(
            "worker_class",
            PulpApiWorker.__module__ + "." + PulpApiWorker.__qualname__,
            enforced=True,
        )

    def load(self):
        using_pulp_api_worker.set(True)

        import pulpcore.app.wsgi

        using_pulp_api_worker.set(False)
        return pulpcore.app.wsgi.application


# Gunicorn options are adapted from:
# https://github.com/benoitc/gunicorn/blob/master/gunicorn/config.py


@click.option(
    "--bind", "-b", default=[f"{ '[::]' if has_ipv6() else '0.0.0.0' }:24817"], multiple=True
)
@click.option("--workers", "-w", type=int)
# @click.option("--threads", "-w", type=int)  # We don't use a threaded worker...
@click.option("--name", "-n", "proc_name")
@click.option("--timeout", "-t", type=int)
@click.option("--graceful-timeout", type=int)
@click.option("--keep-alive", "keepalive", type=int)
@click.option("--limit-request-line", type=int)
@click.option("--limit-request-fields", type=int)
@click.option("--limit-request-field-size", type=int)
@click.option("--max-requests", type=int)
@click.option("--max-requests-jitter", type=int)
@click.option("--access-logfile", "accesslog")
@click.option(
    "--access-logformat",
    "access_log_format",
    default=(
        "pulp [%({correlation-id}o)s]: "
        '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s"',
    ),
)
@click.option("--error-logfile", "--log-file", "errorlog")
@click.option(
    "--log-level", "loglevel", type=click.Choice(["debug", "info", "warning", "error", "critical"])
)
@click.option("--reload/--no-reload")
@click.option("--reload-engine", type=click.Choice(["auto", "poll", "inotify"]))
@click.option("--reload-extra-file", "reload_extra_files", multiple=True)
@click.option("--preload/--no-preload", "preload_app")
@click.option("--reuse-port/--no-reuse-port")
@click.option("--chdir")
@click.option("--user", "-u")
@click.option("--group", "-g")
@click.option(
    "--name-template",
    type=str,
    help="Format string to use for the status name. "
    "'{pid}', '{hostname}', and '{fqdn} will be substituted.",
)
@click.command()
def main(bind, name_template, **options):
    name_template_var.set(name_template)
    options["bind"] = list(bind)
    sys.argv = sys.argv[:1]
    PulpcoreApiApplication(options).run()
