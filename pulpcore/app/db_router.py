import logging
from functools import lru_cache

from django.apps import apps as django_apps
from django.db import router as django_router
from django.db import transaction

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
        "core.progressreport",
        "core.groupprogressreport",
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


def current_alias():
    """The alias a data-plane write/read would resolve to right now via ambient domain
    context -- the same fallback PulpDomainRouter._resolve_db uses once control-plane and
    instance-hint routing have been ruled out."""
    domain = get_domain()
    if domain is not None:
        return _database_alias(domain)
    return "default"


def atomic(using=None, **kwargs):
    """transaction.atomic() that defaults to the ambient routing alias instead of Django's
    always-'default' DEFAULT_DB_ALIAS.

    transaction.atomic() never consults the db_router on its own -- Django requires using=alias
    explicitly, so a bare transaction.atomic() silently opens its transaction on 'default' even
    while the work inside it is routed to a satellite, giving that work no real atomicity at all.

    Only wrap work that belongs to a single alias: Django has no cross-database distributed
    transactions, so mixing a control-plane write (e.g. Task) with a data-plane write in the same
    block still won't be atomic across both, no matter which alias is passed here.
    """
    if using is None:
        using = current_alias()
    return transaction.atomic(using=using, **kwargs)


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

        # Use __dict__ / fields_cache, not getattr/hasattr. FK descriptors can
        # recurse into this router during instance construction or issue an extra query.
        instance = hints.get("instance")
        if instance is not None:
            if "pulp_domain_id" in instance.__dict__:
                domain = instance._state.fields_cache.get("pulp_domain")
                if domain is not None:
                    return _database_alias(domain)

        return current_alias()

    def db_for_read(self, model, **hints):
        return self._resolve_db(model, **hints)

    def db_for_write(self, model, **hints):
        return self._resolve_db(model, **hints)

    def allow_relation(self, obj1, obj2, **hints):
        return True

    def allow_migrate(self, db, app_label, model_name=None, **hints):
        return True


@lru_cache(maxsize=1)
def is_multi_db_routing_active():
    return any(isinstance(r, PulpDomainRouter) for r in django_router.routers)
