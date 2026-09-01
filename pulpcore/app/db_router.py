import logging

from django.apps import apps as django_apps
from django.db import router as django_router

from pulpcore.app.contexts import _current_migration_alias
from pulpcore.app.util import get_domain

logger = logging.getLogger(__name__)

CONTROL_PLANE_LABELS = frozenset(
    {
        "core.domain",
        "core.task",
        "core.taskgroup",
        "core.taskschedule",
        "core.createdresource",
        "core.appstatus",
        "core.systemid",
        "core.accesspolicy",
        "core.role",
        "core.userrole",
        "core.grouprole",
        "core.progressreport",
        "core.groupprogressreport",
        "core.migrationstatus",
        "core.domainmove",
        "core.profileartifact",
        "core.signingservice",
        "core.asciiarmoreddetachedsigningservice",
        "container.manifestsigningservice",
        "rpm.rpmpackagesigningservice",
    }
)

CONTROL_PLANE_APPS = frozenset({"auth", "contenttypes", "admin", "sessions"})


def _database_alias(domain):
    if "database_alias" in domain.__dict__:
        return domain.__dict__["database_alias"]
    return "default"


class PulpDomainRouter:
    def _is_control_plane(self, model):
        label = f"{model._meta.app_label}.{model._meta.model_name}"
        return label in CONTROL_PLANE_LABELS or model._meta.app_label in CONTROL_PLANE_APPS

    def _resolve_db(self, model, **hints):
        if model._meta.apps is not django_apps:
            migration_alias = _current_migration_alias.get()
            if migration_alias is not None:
                return migration_alias

        if self._is_control_plane(model):
            return "default"

        instance = hints.get("instance")
        if instance is not None:
            if "pulp_domain_id" in instance.__dict__:
                domain = instance._state.fields_cache.get("pulp_domain")
                if domain is not None:
                    return _database_alias(domain)

        domain = get_domain()
        if domain is not None:
            return _database_alias(domain)

        return "default"

    def db_for_read(self, model, **hints):
        return self._resolve_db(model, **hints)

    def db_for_write(self, model, **hints):
        return self._resolve_db(model, **hints)

    def allow_relation(self, obj1, obj2, **hints):
        return True

    def allow_migrate(self, db, app_label, model_name=None, **hints):
        return True


def is_multi_db_routing_active():
    return any(isinstance(r, PulpDomainRouter) for r in django_router.routers)
