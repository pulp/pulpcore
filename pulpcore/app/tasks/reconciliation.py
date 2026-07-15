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

This does its own existence check per candidate row (`_target_exists()` below) rather than
resolving through `DomainResolvedGenericRelation.content_object` (`pulpcore.app.models.generic`):
that property must return `None` -- not raise -- for an unresolvable target, since every ordinary
caller (`RelatedResourceField`, `CreatedResourcePrnField`, etc.) treats "target is gone" as a
routine, gracefully-rendered case (e.g. a `Task.created_resources` entry for a since-deleted
`Repository`), not a systemic failure worth surfacing as a 500. This sweep's job is exactly the
opposite -- it needs to *notice* rows whose recorded cross-plane target can't be resolved on the
alias it should live on -- so it queries for existence directly instead of piggy-backing on that
lenient, widely-depended-on property.
"""

from datetime import timedelta
from logging import getLogger

from django.conf import settings
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


def _target_exists(row):
    """
    Resolve whether `row`'s recorded cross-plane target actually exists on its recorded alias.

    Mirrors `DomainResolvedGenericRelation.content_object`'s own resolution (content_type's
    model class, `content_object_domain`'s alias, `object_id`) but as a direct `.exists()`
    check rather than a `.get()` -- this sweep needs a boolean, not the object itself, and must
    not depend on that property's (deliberately lenient) exception behavior.
    """
    model_class = row.content_type.model_class()
    alias = row.content_object_domain.database_alias
    return model_class.objects.using(alias).filter(pk=row.object_id).exists()


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
