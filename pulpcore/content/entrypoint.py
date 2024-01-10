import click
from pulpcore.app.pulpcore_gunicorn_application import PulpcoreGunicornApplication


class PulpcoreContentApplication(PulpcoreGunicornApplication):
    def load_app_specific_config(self):
        self.set_option("default_proc_name", "pulpcore-content", enforced=True)
        self.set_option("worker_class", "aiohttp.GunicornWebWorker", enforced=True)

    def load(self):
        import pulpcore.content

        return pulpcore.content.server


@click.option("--bind", "-b", default="[::]:24816")
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
@click.option("--access-logformat", "access_log_format")
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
    PulpcoreContentApplication(options).run()
