from contextvars import ContextVar
from logging import getLogger
import os
import socket

import click
import django
from django.conf import settings
from django.db import connection
from django.db.utils import InterfaceError, DatabaseError
from gunicorn.workers.sync import SyncWorker

from pulpcore.app.apps import pulp_plugin_configs
from pulpcore.app.pulpcore_gunicorn_application import PulpcoreGunicornApplication

logger = getLogger(__name__)


using_pulp_api_worker = ContextVar("using_pulp_api_worker", default=False)


class PulpApiWorker(SyncWorker):
    def notify(self):
        super().notify()
        self.heartbeat()

    def heartbeat(self):
        try:
            self.api_app_status, created = self.ApiAppStatus.objects.get_or_create(
                name=self.name, defaults={"versions": self.versions}
            )

            if not created:
                self.api_app_status.save_heartbeat()

                if self.api_app_status.versions != self.versions:
                    self.api_app_status.versions = self.versions
                    self.api_app_status.save(update_fields=["versions"])

            logger.debug(self.beat_msg)
        except (InterfaceError, DatabaseError):
            connection.close_if_unusable_or_obsolete()
            logger.info(self.fail_beat_msg)

    def init_process(self):
        os.environ.setdefault("DJANGO_SETTINGS_MODULE", "pulpcore.app.settings")
        django.setup()
        from pulpcore.app.models import ApiAppStatus

        if settings.API_APP_TTL < 2 * self.timeout:
            logger.warn(
                "API_APP_TTL (%s) is smaller than double the gunicorn timeout (%s). "
                "You may experience workers wrongly reporting as missing",
                settings.API_APP_TTL,
                self.timeout,
            )

        self.ApiAppStatus = ApiAppStatus
        self.api_app_status = None

        self.name = "{pid}@{hostname}".format(pid=self.pid, hostname=socket.gethostname())
        self.versions = {app.label: app.version for app in pulp_plugin_configs()}
        self.beat_msg = (
            "Api App '{name}' heartbeat written, sleeping for '{interarrival}' seconds".format(
                name=self.name, interarrival=self.timeout
            )
        )
        self.fail_beat_msg = (
            "Api App '{name}' failed to write a heartbeat to the database, sleeping for "
            "'{interarrival}' seconds."
        ).format(name=self.name, interarrival=self.timeout)
        super().init_process()

    def run(self):
        try:
            super().run()
        finally:
            # cleanup
            if self.api_app_status:
                self.api_app_status.delete()


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


@click.option("--bind", "-b", default="[::]:24817")
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
@click.command()
def main(**options):
    PulpcoreApiApplication(options).run()
