from datetime import timedelta
from logging import getLogger

from django.conf import settings
from django.utils import timezone

from pulpcore.app.models import CreatedResource, ExportedResource
from pulpcore.app.models.role import GroupRole, UserRole

log = getLogger(__name__)

_GFK_MODELS = (CreatedResource, ExportedResource, UserRole, GroupRole)


def _candidate_rows(model, cutoff):
    return model.objects.using("default").filter(
        content_object_domain_id__isnull=False,
        pulp_last_updated__lt=cutoff,
    )


def _target_exists(row):
    model_class = row.content_type.model_class()
    alias = row.content_object_domain.database_alias
    return model_class.objects.using(alias).filter(pk=row.object_id).exists()


def reconcile_cross_plane_references(
    grace_period_minutes=None,
    purge_after_days=None,
    dry_run=False,
):
    if grace_period_minutes is None:
        grace_period_minutes = settings.CROSS_PLANE_RECONCILIATION_GRACE_MINUTES
    if purge_after_days is None:
        purge_after_days = settings.CROSS_PLANE_RECONCILIATION_PURGE_AFTER_DAYS

    cutoff = timezone.now() - timedelta(minutes=grace_period_minutes)
    purge_cutoff = timezone.now() - timedelta(days=purge_after_days) if purge_after_days else None

    report = {"checked": 0, "orphaned": 0, "purged": 0, "orphans": []}

    for model in _GFK_MODELS:
        qs = _candidate_rows(model, cutoff)
        for row in qs.iterator():
            report["checked"] += 1
            if not _target_exists(row):
                alias = row.content_object_domain.database_alias
                age = timezone.now() - row.pulp_last_updated
                log.error(
                    "content_object for %s (pk=%s) not found on alias '%s' "
                    "(content_type_id=%s, object_id=%s). The referenced object may have been "
                    "deleted, or Domain replication for this row's domain may be stale -- run "
                    "'pulpcore-manager sync-domains' to check.",
                    model._meta.label,
                    row.pk,
                    alias,
                    row.content_type_id,
                    row.object_id,
                )
                report["orphaned"] += 1
                report["orphans"].append(
                    {
                        "model": model._meta.label,
                        "pk": str(row.pk),
                        "alias": alias,
                        "age_days": age.days,
                    }
                )
                if not dry_run and purge_cutoff and row.pulp_last_updated < purge_cutoff:
                    log.warning(
                        "Purging orphaned cross-plane row %s (pk=%s, alias=%s, age=%sd) -- "
                        "unresolvable content_object older than "
                        "CROSS_PLANE_RECONCILIATION_PURGE_AFTER_DAYS=%s.",
                        model._meta.label,
                        row.pk,
                        alias,
                        age.days,
                        purge_after_days,
                    )
                    row.delete()
                    report["purged"] += 1

    if report["orphaned"]:
        log.error(
            "Cross-plane reconciliation found %s orphaned reference(s) out of %s checked "
            "(%s purged). See preceding log lines for details on each. Run "
            "'pulpcore-manager reconcile-cross-plane-references' for a full report.",
            report["orphaned"],
            report["checked"],
            report["purged"],
        )
    else:
        log.info(
            "Cross-plane reconciliation checked %s row(s), found no orphans.", report["checked"]
        )

    return report
