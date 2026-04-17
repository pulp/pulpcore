import sys
from importlib.metadata import version as pkg_version

from gunicorn.app.base import Application


def handle_control_interface_feature(options):
    """Drop control_socket from options if gunicorn<25.1, which introduced the feature."""
    # TODO: remove this function when gunicorn lowerbound>=25.1
    if options.get("control_socket") is None:
        return

    gunicorn_version = tuple(int(x) for x in pkg_version("gunicorn").split(".")[:2])
    if gunicorn_version < (25, 1):
        sys.stderr.write(
            "Warning: --control-socket requires gunicorn>=25.1, ignoring "
            f"(installed: {'.'.join(str(x) for x in gunicorn_version)}).\n"
        )
        options["control_socket"] = None


class PulpcoreGunicornApplication(Application):
    """
    A common class for the api and content applications to inherit from that loads the default
    gunicorn configs (including from a config file if one exists) and then overrides with the values
    specified in the init scripts. With warnings / errors if the user overrides something that won't
    take effect or cannot be changed.
    """

    def __init__(self, options):
        self.options = options or {}
        super().__init__()

    def init(self, *args, **kwargs):
        """
        A hook for setting application-specific configs, which we instead do below in load_config
        where it's non-overridable.
        """
        pass

    def set_option(self, key, value, enforced=False):
        if value is None:  # not specified by init script
            return

        def _is_default(key, value):
            if value is None:
                return True
            defaults = {
                "default_proc_name": "gunicorn",
                "reload_extra_files": [],
                "access_log_format": '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s"',
                "bind": ["127.0.0.1:8000"],
                "threads": 1,
                "worker_class": "<class 'gunicorn.workers.sync.SyncWorker'>",
            }
            return key in defaults and str(defaults[key]) == str(value)

        current_value = getattr(self.cfg, key, None)
        if not _is_default(key, current_value) and str(current_value) != str(value):
            if enforced:
                sys.stderr.write(
                    f"Error: {key} is set to {current_value} in gunicorn.conf.py but must not be "
                    "changed!\n"
                )
                exit(1)
            else:
                sys.stderr.write(
                    f"Warning: {key} is set to {current_value} in gunicorn.conf.py but is "
                    f"overridden to {value} by init script!\n"
                )

        self.cfg.set(key, value)

    def load_config(self):
        # Load default gunicorn configs, including reading from the default config file.
        super().load_config()
        # Override with settings that we've specified in the startup script.
        for key, value in self.options.items():
            self.set_option(key, value)
        self.set_option("threads", "1", enforced=True)
        self.load_app_specific_config()

    def load_app_specific_config(self):
        raise NotImplementedError

    def load(self):
        raise NotImplementedError
