"""
Domain-aware database router (Phase 1, Layer 1 of the query architecture).

`PulpDomainRouter` splits models into a "control plane" (always on the `default` database
alias -- Task, Domain itself, RBAC, Django built-ins, etc.) and a "data plane" (routed by the
owning `Domain.database_alias` -- repositories, content, artifacts, and every plugin-defined
model). See `architecture/domain-db-offloading-design.md` for the full design.

This router is only registered in `DATABASE_ROUTERS` when more than one database alias is
configured (see `pulpcore/app/settings.py`) -- for the overwhelmingly common single-database
deployment, Django's own routing (`django.db.utils.ConnectionRouter._route_db`) never even
consults `self.routers` when it is empty, so this module has zero runtime cost unless a second
alias is actually configured.
"""

import logging

from django.apps import apps as django_apps

from pulpcore.app.contexts import _current_migration_alias
from pulpcore.app.util import get_domain

logger = logging.getLogger(__name__)

#: Control-plane models: coordination/bookkeeping data that must always live on the same
#: physical database as the worker/task coordination primitives (`pg_notify`, advisory locks,
#: `SELECT ... FOR UPDATE SKIP LOCKED`), which require a single PostgreSQL instance (see the
#: design doc's "Why Control Plane Stays on the Original RDS"). `Domain` itself is here too: it
#: is authoritative on `default` and merely replicated (read-only, from the routing
#: perspective) to every other alias.
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
        # Fleet-wide migration-orchestration bookkeeping (phase1-migrate-all) -- describes the
        # aliases themselves, not any one domain's data.
        "core.migrationstatus",
        # Historical record of `move-domain` runs (phase2-move-domain) -- fleet-management
        # metadata about *when*/*between which aliases* a domain moved, not domain data itself.
        "core.domainmove",
        # ProfileArtifact spans Task (control) and Artifact (data) -- KI-03. It is kept on the
        # control DB alongside Task, its FK cascade parent; the `artifact` FK is a documented
        # cross-plane exception handled explicitly (KI-02), not via the router.
        "core.profileartifact",
        # SigningService (and every plugin's multi-table-inheritance subtype) has no
        # `pulp_domain` field at all -- it's a genuinely global, shared-across-domains resource
        # (e.g. one signing key used by repositories in many different domains), not
        # domain-scoped data. Without this entry it would fall through to the router's
        # ContextVar fallback and get silently written to whatever domain happens to be in
        # context for the current request/task (e.g. `add-signing-service` run while a
        # domain-scoped task is executing), making it invisible to every other domain
        # (management-command-audit.md finding). New plugin SigningService subtypes must be
        # added here too.
        "core.signingservice",
        "core.asciiarmoreddetachedsigningservice",
        "container.manifestsigningservice",
        "rpm.rpmpackagesigningservice",
    }
)

#: Django/contrib apps whose tables are pure framework bookkeeping and always stay on `default`.
CONTROL_PLANE_APPS = frozenset({"auth", "contenttypes", "admin", "sessions"})


class PulpDomainRouter:
    """
    Routes data-plane models to the database alias of the `Domain` they belong to, and pins
    control-plane models (and Django's own built-in apps) to `default`.

    Resolution order for data-plane models (see "Known Router Limitations and Mitigations" in
    the design doc):

    1. **Instance hint** -- if Django passes the actual model instance being saved/read (most
       reliable; e.g. `instance.save()`), and it already has an *in-memory* `pulp_domain_id` and
       a *cached* `pulp_domain` relation object (e.g. via `select_related("pulp_domain")`, or
       because the domain was explicitly assigned), use `pulp_domain.database_alias`. This never
       triggers a fresh query or a `refresh_from_db()` call -- see the inline comments in
       `_resolve_db` (KI-27) for why both of those are unsafe here.
    2. **ContextVar** -- set by `DomainMiddleware` for every HTTP request and by
       `with_task_context()` for every task; covers the common API/task code path where Django
       does not pass an instance hint (e.g. `Model.objects.filter(...)`).
    3. **Safe default** -- `"default"`. If a domain has since been moved to a satellite and its
       rows cleaned up from `default`, this returns empty results rather than corrupt data; if
       cleanup hasn't run yet, it returns the (still valid) stale copy. Never guesses wrong in a
       way that mixes data from two different domains.
    """

    def _is_control_plane(self, model):
        label = f"{model._meta.app_label}.{model._meta.model_name}"
        return label in CONTROL_PLANE_LABELS or model._meta.app_label in CONTROL_PLANE_APPS

    def _resolve_db(self, model, **hints):
        # `apps.get_model(...)` inside a `RunPython` data migration returns a "historical" model
        # bound to a per-migration `StateApps` registry, never to the live global one -- a cheap,
        # reliable way to tell "this query was issued from inside a migration" apart from
        # ordinary app code (see `pulpcore.app.management.commands.migrate` for the full
        # rationale). Every pre-existing migration queries these historical models with no
        # explicit `.using(...)`, exactly as Django's single-database docs recommend, so without
        # this check the control-plane pin below (or the domain ContextVar fallback) would
        # silently redirect the query away from whichever alias `migrate` is actually operating
        # on -- a no-op as long as every alias's schema+data happens to be in lockstep, but wrong
        # the instant they aren't (e.g. `migrate-all` always finishes migrating `default` first).
        if model._meta.apps is not django_apps:
            migration_alias = _current_migration_alias.get()
            if migration_alias is not None:
                return migration_alias

        if self._is_control_plane(model):
            return "default"

        instance = hints.get("instance")
        if instance is not None:
            # Inspect `instance.__dict__` directly instead of `hasattr()`/`getattr()`. Both of
            # those go through `pulp_domain_id`'s `DeferredAttribute.__get__` (every concrete
            # Django field, FK attnames included, gets one via `Field.contribute_to_class`), and
            # that descriptor's fallback path (`data[field_name] not in data -> ...
            # instance.refresh_from_db(fields=[field_name])`) fires whenever `pulp_domain_id`
            # hasn't been *set* on this exact instance yet -- not just for instances loaded with
            # `.defer()`/`.only()`, but for any brand-new, still-under-construction instance
            # whose class declares another FK *before* `pulp_domain` in field order (e.g.
            # `RemoteArtifact`: `content_artifact`, `remote`, then `pulp_domain` -- see
            # `models/content.py`). Assigning one of those earlier FKs re-enters the router via
            # `ForwardManyToOneDescriptor.__set__` (`instance._state.db = router.db_for_write(...,
            # instance=<the other side>)`), which passes *this* half-built instance right back in
            # as the hint -- and since `instance._is_pk_set()` is already true (the PK field is
            # processed before any FK in `_meta.concrete_fields` order and has a `default=uuid4`),
            # `DeferredAttribute.__get__` takes the `refresh_from_db()` branch instead of the
            # "unsaved, no PK yet" `AttributeError` branch, which calls back into the router with
            # the *same* instance and recurses until `RecursionError` (KI-27). A plain
            # `"pulp_domain_id" in instance.__dict__` membership check never invokes the
            # descriptor at all, so it can't trigger that fallback -- it only ever reports
            # whether a value has *actually* been stored on this instance already, which is
            # exactly what "instance hint" routing should be asking.
            if "pulp_domain_id" in instance.__dict__:
                # Likewise, don't `getattr(instance, "pulp_domain", None)`: if the FK id is set
                # but the related `Domain` row hasn't been fetched (e.g. the instance was loaded
                # without `select_related("pulp_domain")`), the descriptor `__get__` would issue
                # a fresh query for it on every single call -- a silent N+1 on top of whatever
                # relation access or write triggered this router call in the first place (KI-27;
                # reproduced by `test_base.py::test_cast` under multi-DB, which expects exactly 1
                # query for `repository.remote` and got 2 once a real `Domain` fetch was mixed
                # in). Reading straight from `instance._state.fields_cache` only ever returns a
                # value Django already fetched for some other reason (`select_related`, a prior
                # `.pulp_domain` access, or the object being explicitly assigned); it never
                # issues a query of its own. If the `Domain` isn't already cached, fall through
                # to the ContextVar/default resolution below rather than paying for a fetch here.
                domain = instance._state.fields_cache.get("pulp_domain")
                if domain is not None:
                    return getattr(domain, "database_alias", "default")

        domain = get_domain()
        if domain is not None:
            return getattr(domain, "database_alias", "default")

        return "default"

    def db_for_read(self, model, **hints):
        return self._resolve_db(model, **hints)

    def db_for_write(self, model, **hints):
        return self._resolve_db(model, **hints)

    def allow_relation(self, obj1, obj2, **hints):
        # Cross-DB FKs (e.g. cross-plane models) are allowed at the Django level; the "no
        # cross-DB join" restriction is enforced at the query layer (CrossDBQuerySetMixin,
        # explicit .using() in Layer 3/4 code), not here. Returning True everywhere avoids
        # Django raising spurious "relations across databases" errors for FKs we intentionally
        # allow to span planes (e.g. Export.task -- see KI-23).
        return True

    def allow_migrate(self, db, app_label, model_name=None, **hints):
        # Identical schema on every alias (accepted trade-off, see KI-16): every RDS instance,
        # satellite or original, gets the full pulpcore + plugin schema so that `allow_migrate`
        # never has to reason about which tables "belong" on which alias.
        return True
