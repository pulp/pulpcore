"""
KI-11 reconciliation: periodic sweep for orphaned cross-plane `GenericForeignKey` references.

There is no distributed transaction spanning `default` (control plane) and a satellite alias
(data plane) -- e.g. a task can write its `CreatedResource` row on `default` and then crash (or
the process can be killed) before/without the corresponding data-plane write ever landing on the
satellite, or a domain can be moved/cleaned-up (`move-domain` / `cleanup-moved-domain`) while a
handful of in-flight cross-plane rows still point at the old alias. This is an accepted trade-off
(see the design doc's KI-11 and "No Distributed Transactions" sections), mitigated by detecting
and reporting (optionally purging) the resulting orphans here rather than by trying to eliminate
them.

This reuses the KI-18 `content_object` resolver (`DomainResolvedGenericRelation`, see
`pulpcore.app.models.generic`) as the *only* detection mechanism: every model in scope already
raises loudly (logs + re-raises `DoesNotExist`) when a cross-plane `content_object` can't be
resolved on its recorded alias, so this sweep doesn't need any separate orphan-detection logic --
it just needs to iterate the candidate rows and call `.content_object` on each.
"""

from datetime import timedelta
from logging import getLogger

from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist
from django.utils import timezone

from pulpcore.app.models import CreatedResource, ExportedResource
from pulpcore.app.models.role import GroupRole, UserRole

log = getLogger(__name__)

#: Every model that mixes in `DomainResolvedGenericRelation` (KI-18) and can therefore hold a
#: stale cross-plane `content_object` reference. Kept in one place so a new such model only needs
#: adding here to be covered by this sweep.
_GFK_MODELS = (CreatedResource, ExportedResource, UserRole, GroupRole)


def _candidate_rows(model, cutoff):
    """
    Rows of `model` worth checking: those with a recorded cross-plane target
    (`content_object_domain_id` set -- same-plane targets can't suffer from KI-18 at all, since
    they're always resolved on this row's own alias) that are old enough that a resolution
    failure is meaningfully suspicious rather than ordinary in-flight lag.
    """
    return model.objects.using("default").filter(
        content_object_domain_id__isnull=False,
        pulp_last_updated__lt=cutoff,
    )


def reconcile_cross_plane_references(
    grace_period_minutes=None,
    purge_after_days=None,
    dry_run=False,
):
    """
    Sweep `CreatedResource`/`ExportedResource`/`UserRole`/`GroupRole` for orphaned cross-plane
    `content_object` references and report (optionally purge) them.

    Args:
        grace_period_minutes (int): Rows updated more recently than this are skipped (still
            "fresh enough" that a resolution failure is more likely ordinary replication lag than
            a real orphan). Defaults to `settings.CROSS_PLANE_RECONCILIATION_GRACE_MINUTES`.
        purge_after_days (int): Confirmed orphans older than this many days are deleted outright.
            `0`/`None` (the default, from `settings.CROSS_PLANE_RECONCILIATION_PURGE_AFTER_DAYS`)
            disables purging -- orphans are only ever logged/reported.
        dry_run (bool): If True, never delete anything regardless of `purge_after_days`; only
            report what would happen. Used by `reconcile-cross-plane-references --dry-run`.

    Returns:
        dict: Per-model counts of `checked`, `orphaned`, and `purged` rows, plus a flat list of
        `orphans` describing each unresolvable row (model label, pk, alias, age).
    """
    if grace_period_minutes is None:
        grace_period_minutes = settings.CROSS_PLANE_RECONCILIATION_GRACE_MINUTES
    if purge_after_days is None:
        purge_after_days = settings.CROSS_PLANE_RECONCILIATION_PURGE_AFTER_DAYS

    cutoff = timezone.now() - timedelta(minutes=grace_period_minutes)
    purge_cutoff = timezone.now() - timedelta(days=purge_after_days) if purge_after_days else None

    report = {"checked": 0, "orphaned": 0, "purged": 0, "orphans": []}

    # Deliberately no `ProgressReport` here (unlike e.g. `orphan_cleanup`): `ProgressReport.task`
    # is a required (non-nullable) FK, so it can only be used from inside a dispatched task's own
    # execution context (`Task.current()` set). This function is also called directly by the
    # 'reconcile-cross-plane-references' management command for on-demand/manual runs, with no
    # task at all -- plain logging works in both contexts.
    for model in _GFK_MODELS:
        qs = _candidate_rows(model, cutoff)
        for row in qs.iterator():
            report["checked"] += 1
            try:
                row.content_object
            except ObjectDoesNotExist:
                # The resolver (DomainResolvedGenericRelation.content_object) already logged the
                # specifics (model/pk/alias/content_type); we just tally here.
                report["orphaned"] += 1
                alias = (
                    row.content_object_domain.database_alias
                    if row.content_object_domain_id
                    else None
                )
                age = timezone.now() - row.pulp_last_updated
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
