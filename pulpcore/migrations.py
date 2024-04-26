from packaging.version import parse as parse_version

from django.conf import settings
from django.utils import timezone
from django.db.migrations.operations.base import Operation


class RequireVersion(Operation):
    reversible = True

    def __init__(self, plugin, version, hints=None):
        self.plugin = plugin
        self.version = version
        self.hints = hints or {}
        self.elidable = True

    def state_forwards(self, app_label, state):
        pass

    def state_backwards(self, app_label, state):
        pass

    def database_forwards(self, app_label, schema_editor, from_state, to_state):
        from_state.clear_delayed_apps_cache()
        ApiAppStatus = from_state.apps.get_model("core", "ApiAppStatus")
        ContentAppStatus = from_state.apps.get_model("core", "ContentAppStatus")
        Worker = from_state.apps.get_model("core", "Worker")

        needed_version = parse_version(self.version)
        errors = []

        for worker_class, ttl, class_name in [
            (ApiAppStatus, settings.API_APP_TTL, "api server"),
            (ContentAppStatus, settings.CONTENT_APP_TTL, "content server"),
            (Worker, settings.WORKER_TTL, "pulp worker"),
        ]:
            for worker in worker_class.objects.filter(
                last_heartbeat__gte=timezone.now() - timezone.timedelta(seconds=ttl)
            ):
                present_version = worker.versions.get(self.plugin)
                if present_version is not None and parse_version(present_version) < needed_version:
                    errors.append(
                        f"  - '{self.plugin}'='{present_version}' "
                        f"with {class_name} '{worker.name}'"
                    )

        if errors:
            raise RuntimeError(
                "\n".join(
                    [
                        "Incompatible versions detected "
                        f"({self.plugin} >= {self.version} needed):",
                        *errors,
                        "Please shutdown or upgrade the outdated components before you "
                        "continue the migration.",
                    ]
                )
            )

    def database_backwards(self, app_label, schema_editor, from_state, to_state):
        pass

    def describe(self):
        return f"Require plugin '{self.plugin}' >= '{self.version}'."

    @property
    def migration_name_fragment(self):
        return f"require_{self.plugin}_{self.version}"
