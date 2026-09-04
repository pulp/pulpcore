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
    "core.exportedresource": "export__pulp_domain_id",
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
    pass


def data_plane_models():
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
            continue
        models.append((model, lookup))
    return models


def _domain_queryset(model, lookup, alias, domain):
    return model.objects.using(alias).filter(**{lookup: domain.pk})


def estimate_domain_size(domain, alias):
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
                value = value.name
            values[field.attname] = value
        instance = model(**values)
        instance._state.adding = False
        if isinstance(instance, LifecycleModelMixin):
            instance.save(using=target_alias, skip_hooks=True)
        else:
            instance.save(using=target_alias)
        copied += 1
    return copied


def copy_domain_data(domain, source_alias, target_alias):
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
    from pulpcore.constants import DOMAIN_MOVE_LOCK

    return _advisory_lock(
        DOMAIN_MOVE_LOCK,
        "Could not acquire the domain-move advisory lock. Another 'move-domain' run is "
        "already in progress.",
    )
