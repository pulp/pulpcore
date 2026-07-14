"""
Shared helpers for the `move-domain` and `cleanup-moved-domain` management commands
(phase2-move-domain / phase2-cleanup), implementing Strategy A ("Read-Only Cutover") from
`architecture/domain-db-offloading-design.md`'s "Domain Movement Procedure".

Data copy uses Option B from the design doc (application-level Django read+write, filtered by
`pulp_domain_id`) rather than Option A (`pg_dump --where`, requires pg_dump >= 16) or Option C
(`dblink`/`postgres_fdw`, requires network access configured between the two RDS instances
specifically for this purpose): Option B needs nothing beyond the ordinary Django DB connections
this process already holds to every configured alias, at the cost of being slower for very large
domains. Operators with `pg_dump` >= 16 or `postgres_fdw` connectivity already set up between
their RDS instances may prefer Option A/C for a large domain instead -- this module does not
implement either, but nothing here precludes running them manually and then using
`move-domain --skip-copy` (see the command) to drive the rest of the procedure (verification
through cutover) against data copied out-of-band.
"""

import logging
from contextlib import contextmanager

from django.apps import apps as django_apps
from django.db import IntegrityError, connections
from django.db.models import ProtectedError, RestrictedError
from django.db.models.fields.files import FileField
from django_lifecycle.mixins import LifecycleModelMixin

from pulpcore.app.contexts import with_domain
from pulpcore.app.db_router import PulpDomainRouter

logger = logging.getLogger(__name__)

_router = PulpDomainRouter()

#: Data-plane models (per the router's classification -- `PulpDomainRouter._is_control_plane`)
#: that don't carry their own `pulp_domain` field, so `data_plane_models()`'s generic
#: `hasattr(model, "pulp_domain_id")` check can't find them: mostly `ManyToManyField(through=)`
#: join tables (`ContentArtifact`, `RepositoryContent`, `PublishedArtifact`, ...), plus a handful
#: of models that are domain-scoped only transitively through a required FK
#: (`RepositoryVersion` -> `Repository`, most notably). Maps `app_label.model_name` to the
#: lookup used to filter that model's rows down to one domain -- found by an exhaustive
#: full-codebase pass (every concrete, non-control-plane model without a `pulp_domain` field,
#: for pulpcore core + every plugin enabled while auditing this), not by inspection of any one
#: app in isolation. A new plugin-defined model of this same shape must be added here too, or
#: `move-domain`/`cleanup-moved-domain` will silently skip its rows -- `copy_domain_data`'s
#: retry-pass loop turns a missing entry here into a hard failure (an unresolvable FK
#: dependency, since the referencing model's own domain-scoped rows never get copied at all)
#: rather than a silent data loss, so a gap here is at least loud, not silent.
THROUGH_MODEL_DOMAIN_FILTERS = {
    "core.contentartifact": "content__pulp_domain_id",
    "core.repositorycontent": "repository__pulp_domain_id",
    "core.repositoryversion": "repository__pulp_domain_id",
    "core.repositoryversioncontentdetails": "repository_version__repository__pulp_domain_id",
    "core.publishedartifact": "publication__pulp_domain_id",
    "core.distributedpublication": "distribution__pulp_domain_id",
    "core.alternatecontentsourcepath": "alternate_content_source__pulp_domain_id",
    "core.pulpimporterrepository": "repository__pulp_domain_id",
    "core.uploadchunk": "upload__pulp_domain_id",
    # ExportedResource (like CreatedResource/UserRole/GroupRole) has no domain field of its own
    # -- its `export` FK is what's actually domain-scoped (unlike CreatedResource's `task`,
    # which is control-plane, `Export` itself *is* data-plane, see exporter.py).
    "core.exportedresource": "export__pulp_domain_id",
    # Plugin models found by the same exhaustive pass, extended to every plugin installed while
    # auditing this (pulp_container, pulp_rpm, pulp_python) -- confirmed empty for pulp_npm,
    # pulp_maven, pulp_hugging_face(_local) (every data-plane model they define already has its
    # own `pulp_domain` field). pulp_ostree was not installed in the environment this audit ran
    # in and could not be checked -- verify it before relying on this registry for a pulp_ostree
    # domain move.
    "container.blobmanifest": "manifest__pulp_domain_id",
    "container.manifestlistmanifest": "manifest_list__pulp_domain_id",
    "rpm.addon": "distribution_tree__pulp_domain_id",
    "rpm.checksum": "distribution_tree__pulp_domain_id",
    "rpm.image": "distribution_tree__pulp_domain_id",
    "rpm.variant": "distribution_tree__pulp_domain_id",
    "rpm.rpmpackagesigningresult": "result_package__pulp_domain_id",
    "rpm.updatecollection": "update_record__pulp_domain_id",
    "rpm.updatereference": "update_record__pulp_domain_id",
    "rpm.updatecollectionpackage": "update_collection__update_record__pulp_domain_id",
    "python.pythonblocklistentry": "repository__pulp_domain_id",
}


class DomainMoveError(Exception):
    """Raised for any unrecoverable problem moving/cleaning up a domain's data.

    Deliberately not a Django `CommandError` -- this module is imported by more than one
    management command, none of which should have to import Django's management-command
    machinery just to catch this.
    """


def data_plane_models():
    """
    Every concrete, non-proxy model the router treats as data-plane (see
    `PulpDomainRouter._is_control_plane`) together with the field/lookup used to filter its rows
    down to one domain, across pulpcore and every installed plugin.

    Returns a list of `(model, lookup)` tuples. Ordering is whatever `apps.get_models()` returns
    (app-registration order) -- callers that care about FK dependency order (`copy_domain_data`,
    `delete_domain_data`) use a retry-pass loop instead of relying on this order being correct,
    since neither `apps.get_models()` nor a plugin's declaration order is guaranteed to already
    be topologically sorted by FK dependency (e.g. multi-table-inheritance parents must be
    written/deleted in the opposite order from each other).
    """
    models = []
    for model in django_apps.get_models():
        if model._meta.proxy or model._meta.auto_created:
            continue
        if _router._is_control_plane(model):
            continue
        if hasattr(model, "pulp_domain_id"):
            models.append((model, "pulp_domain_id"))
    for label, lookup in THROUGH_MODEL_DOMAIN_FILTERS.items():
        try:
            model = django_apps.get_model(label)
        except LookupError:
            # Not every entry's plugin is necessarily installed in a given deployment (e.g. an
            # rpm.* entry when pulp_rpm isn't enabled) -- nothing to copy/delete/verify for a
            # model that doesn't exist here at all.
            continue
        models.append((model, lookup))
    return models


def _domain_queryset(model, lookup, alias, domain):
    return model.objects.using(alias).filter(**{lookup: domain.pk})


def estimate_domain_size(domain, alias):
    """
    Step 1 size estimate (design doc): for every data-plane model, this domain's own row count
    on `alias` plus that table's total on-disk size for scale/context.

    Mirrors the design doc's own example SQL exactly (`SELECT COUNT(*),
    pg_total_relation_size(...) FROM <table> WHERE pulp_domain_id = <pk>`): Postgres has no
    built-in function for "the on-disk size of just these rows", so `table_total_size_bytes`
    below is the size of the *entire* table (data + indexes + TOAST, shared across every domain
    that has rows in it), not this domain's share of it -- read it as "this table could be at
    most this big", not "this domain's data is this many bytes". `row_count` is the number that
    is actually domain-specific.

    Returns a list of dicts, one per data-plane model, each with `model`, `table`, `row_count`,
    and `table_total_size_bytes` keys.
    """
    rows = []
    for model, lookup in data_plane_models():
        count = _domain_queryset(model, lookup, alias, domain).count()
        table = model._meta.db_table
        with connections[alias].cursor() as cursor:
            cursor.execute("SELECT pg_total_relation_size(%s)", [table])
            (table_size,) = cursor.fetchone()
        rows.append(
            {
                "model": model._meta.label,
                "table": table,
                "row_count": count,
                "table_total_size_bytes": table_size or 0,
            }
        )
    return rows


def _run_passes(models, action, action_description):
    """
    Repeatedly apply `action(model, lookup)` to every entry in `models`, deferring any model
    that raises an FK-dependency error to a later pass, until either every model has succeeded
    or a full pass makes no further progress at all.

    This is the mechanism that makes `copy_domain_data`/`delete_domain_data` correct without
    needing to hand-maintain a topological sort of every pulpcore+plugin model's FK graph: a
    multi-table-inheritance child (or any other FK-dependent row) simply fails with an
    `IntegrityError` (copy: missing parent row) or `ProtectedError`/`RestrictedError` (delete:
    still-referenced row) on whichever pass runs before its dependency is satisfied, and
    succeeds on a later one once that dependency has been handled. "No progress in a full pass"
    means every remaining model is blocked on something *other* than one of its still-remaining
    siblings (e.g. a real bug, or a plugin FK to a model this module doesn't know is
    domain-scoped) -- that's the only case treated as a hard failure.
    """
    remaining = list(models)
    results = {}
    while remaining:
        blocked = []
        progressed = False
        for model, lookup in remaining:
            try:
                results[model._meta.label] = action(model, lookup)
            except (IntegrityError, ProtectedError, RestrictedError):
                blocked.append((model, lookup))
            else:
                progressed = True
        if not progressed:
            raise DomainMoveError(
                f"Could not {action_description} for: "
                f"{', '.join(model._meta.label for model, _ in blocked)} "
                f"(unresolved FK dependency -- see data_plane_models()/"
                f"THROUGH_MODEL_DOMAIN_FILTERS if this is a plugin model this module doesn't "
                f"know about)."
            )
        remaining = blocked
    return results


def _copy_model(model, lookup, domain, source_alias, target_alias):
    fields = model._meta.concrete_fields
    copied = 0
    for row in _domain_queryset(model, lookup, source_alias, domain).iterator():
        values = {}
        for field in fields:
            value = getattr(row, field.attname)
            if isinstance(field, FileField) and value:
                # Object storage is shared/global infrastructure and is never moved by a
                # domain move (design doc, "Object storage" section) -- only this row's
                # *reference* to the already-existing blob moves, not the blob itself. Passing
                # the bound `FieldFile` through as-is would make `ArtifactFileField.pre_save`
                # (see pulpcore.app.models.fields) think a *newly uploaded* file needs to be
                # moved into place, and try to open it by its bare relative name relative to
                # the process's cwd -- not the storage backend -- which fails outright. Passing
                # the plain stored path string instead makes the freshly-constructed `FieldFile`
                # default to `_committed=True` (see `FieldFile.__init__`), so `pre_save`
                # correctly treats it as already in place, with no file I/O at all.
                value = value.name
            values[field.attname] = value
        instance = model(**values)
        # `_state.adding` forced to False *before* saving, so Django's own `_save_table()` takes
        # its normal "try UPDATE (by pk), fall back to INSERT" path instead of the special-case
        # optimization it applies to any freshly *constructed* instance whose pk field has a
        # `default=` (true for every pulpcore model's `pulp_id`, via `pulp_uuid`): that
        # optimization forces an unconditional INSERT purely because the instance was just
        # constructed in Python, *regardless* of whether its pk was then explicitly overwritten
        # to an already-existing value -- so re-running a partially-completed copy would always
        # raise `IntegrityError` on every row a previous, interrupted run already copied. This
        # matters even more for multi-table-inheritance models (e.g. `FileContent`): `_state`
        # is shared across the *whole* instance, not per-table, so without this, a `FileContent`
        # copy would also try to force-INSERT its already-existing `Content` parent-table row
        # (if an earlier, separate pass already copied `Content` on its own) and fail the exact
        # same way -- forcing `not adding` makes each table level independently try UPDATE first,
        # which is exactly the "insert whichever levels don't exist yet, no-op update the rest"
        # behavior a safe-to-re-run copy needs. `domain_sync.py`'s replicator does not need this
        # trick because it always fetches the existing target row (if any) *before* constructing,
        # rather than relying on this after-the-fact override -- either approach works, but a
        # get-or-construct dance for every one of the ~40 data-plane models here (some behind an
        # indirect lookup, not a plain pk fetch) would be considerably more code for the same
        # result.
        instance._state.adding = False
        # skip_hooks=True: this is a verbatim copy of already-validated data, not a new
        # create/update action -- lifecycle hooks (role creation, validation, etc.) must not
        # re-fire for it. Only for models that are actually django-lifecycle-enabled though: a
        # handful of data-plane models (e.g. `RepositoryVersionContentDetails`) are plain
        # `models.Model` and don't accept the `skip_hooks` kwarg at all.
        if isinstance(instance, LifecycleModelMixin):
            instance.save(using=target_alias, skip_hooks=True)
        else:
            instance.save(using=target_alias)
        copied += 1
    return copied


def copy_domain_data(domain, source_alias, target_alias):
    """
    Step 3 (Option B) of the design doc's Read-Only Cutover procedure: copy every data-plane row
    belonging to `domain` from `source_alias` to `target_alias`.

    Returns a `{model_label: row_count_copied}` dict. Safe to re-run (see `_copy_model`).

    Runs with the domain ContextVar set to `domain` (`with_domain`): `Artifact`'s storage path
    (`pulpcore.app.models.storage.get_artifact_path`) and the field-level `DomainStorage` proxy
    both resolve the *current* domain from that ContextVar, not from any instance being saved --
    without this, saving a copied `Artifact` row would compute storage paths as if it belonged
    to whichever domain (typically "default") happened to be in context when this function was
    called, silently mismatching the path the blob was actually written under.
    """
    with with_domain(domain):
        return _run_passes(
            data_plane_models(),
            lambda model, lookup: _copy_model(model, lookup, domain, source_alias, target_alias),
            "copy data",
        )


def _row_checksum(pks):
    import hashlib

    return hashlib.sha256(",".join(sorted(str(pk) for pk in pks)).encode()).hexdigest()


def verify_domain_data(domain, source_alias, target_alias):
    """
    Step 4 of the design doc's procedure: for every data-plane model, compare row counts and a
    checksum (SHA-256 over the sorted set of primary keys) between `source_alias` and
    `target_alias` for this domain's rows.

    Returns a list of mismatch dicts (empty list means the copy verified clean). Each dict has
    `model`, `source_count`, `target_count`, `source_checksum`, `target_checksum`.
    """
    mismatches = []
    for model, lookup in data_plane_models():
        source_pks = list(
            _domain_queryset(model, lookup, source_alias, domain).values_list("pk", flat=True)
        )
        target_pks = list(
            _domain_queryset(model, lookup, target_alias, domain).values_list("pk", flat=True)
        )
        source_checksum = _row_checksum(source_pks)
        target_checksum = _row_checksum(target_pks)
        if len(source_pks) != len(target_pks) or source_checksum != target_checksum:
            mismatches.append(
                {
                    "model": model._meta.label,
                    "source_count": len(source_pks),
                    "target_count": len(target_pks),
                    "source_checksum": source_checksum,
                    "target_checksum": target_checksum,
                }
            )
    return mismatches


def _delete_model(model, lookup, domain, alias):
    return _domain_queryset(model, lookup, alias, domain).delete()[0]


def delete_domain_data(domain, alias):
    """
    Step 7 (cleanup) of the design doc's procedure: delete every data-plane row belonging to
    `domain` from `alias`.

    Used by `cleanup-moved-domain` to remove the stale copy left on the original alias after a
    move has been verified in production; the retry-pass mechanism (`_run_passes`) handles the
    FK ordering needed to delete e.g. a `ContentArtifact` row before the `Artifact`/`Content`
    rows it `PROTECT`s, without this module needing to hand-maintain that ordering.

    Returns a `{model_label: row_count_deleted}` dict.
    """
    return _run_passes(
        data_plane_models(),
        lambda model, lookup: _delete_model(model, lookup, domain, alias),
        "delete data",
    )


@contextmanager
def _advisory_lock(lock_id, error_message):
    with connections["default"].cursor() as cursor:
        cursor.execute("SELECT pg_try_advisory_lock(%s)", [lock_id])
        (acquired,) = cursor.fetchone()
        if not acquired:
            raise DomainMoveError(error_message)
        try:
            yield
        finally:
            cursor.execute("SELECT pg_advisory_unlock(%s)", [lock_id])


def domain_move_lock():
    """Advisory lock held for the duration of a `move-domain` run (see `DOMAIN_MOVE_LOCK`)."""
    from pulpcore.constants import DOMAIN_MOVE_LOCK

    return _advisory_lock(
        DOMAIN_MOVE_LOCK,
        "Could not acquire the domain-move advisory lock. Another 'move-domain' run is "
        "already in progress.",
    )
