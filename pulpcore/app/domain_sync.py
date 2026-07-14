"""
Write-through replication of the `Domain` table to every configured satellite alias.

`Domain` is a control-plane model: it is authoritative on the `default` database alias, but a
read-only copy of every `Domain` row must also exist on every other configured `DATABASES` alias
so that per-process code (the router, `for_each_domain()`, `Domain.get_storage()`, etc.) can
resolve `database_alias`/`storage_settings`/`moving` without ever needing a cross-database query
(see KI-14/KI-15 in the design doc).

Two mechanisms keep satellites in sync:

* `post_save`/`post_delete` signals (connected in `apps.py`) push individual changes as they
  happen, with retry + exponential backoff. Best-effort: a replication failure here is logged
  loudly but does not fail the triggering request/task.
* The `sync-domains` management command performs a full reconciliation pass, which is required
  to catch anything the signals miss (`bulk_create()`/`.update()` bypass Django signals
  entirely -- KI-15 -- and a satellite that was down when a signal fired never gets the retried
  write once it comes back, until reconciliation runs).
"""

import logging
import time

from django.conf import settings

logger = logging.getLogger(__name__)

#: Number of attempts made to replicate a single Domain change to a single alias.
REPLICATION_RETRY_ATTEMPTS = 3
#: Initial delay (seconds) between replication retries; doubled after each failed attempt.
REPLICATION_RETRY_BACKOFF = 1


def satellite_aliases():
    """Return every configured `DATABASES` alias other than `"default"`."""
    return [alias for alias in settings.DATABASES if alias != "default"]


def domain_field_values(domain):
    """Return a dict of `{attname: value}` for every concrete field on a Domain instance.

    Used to build the `defaults` payload written to satellite aliases, and (minus
    `pulp_last_updated`, see `_comparable_domain_field_values`) by `sync-domains` to compare rows
    across aliases.
    """
    return {field.attname: getattr(domain, field.attname) for field in domain._meta.concrete_fields}


def _comparable_domain_field_values(domain):
    """Like `domain_field_values`, but excludes `pulp_last_updated` for drift comparisons.

    `pulp_last_updated` is `auto_now=True` (see `BaseModel`), so it is unconditionally
    overwritten to "now" by Django on every `.save()` call -- including every replication write
    to a satellite. Comparing it verbatim would make a freshly-replicated row look "stale" again
    on the very next `reconcile_domains_to_alias` pass, forcing a needless rewrite every time
    `sync-domains` runs even with zero real drift.
    """
    values = domain_field_values(domain)
    values.pop("pulp_last_updated", None)
    return values


def replicate_domain_save(domain, using=None, attempts=REPLICATION_RETRY_ATTEMPTS):
    """Push a single Domain row to every satellite alias (write-through replication)."""
    aliases = satellite_aliases()
    if not aliases:
        return
    values = domain_field_values(domain)
    pulp_id = values.pop("pulp_id")
    for alias in aliases:
        if alias == using:
            continue
        _replicate_one_save(alias, pulp_id, values, attempts)


def replicate_domain_delete(pulp_id, using=None, attempts=REPLICATION_RETRY_ATTEMPTS):
    """Delete a single Domain row from every satellite alias."""
    aliases = satellite_aliases()
    if not aliases:
        return
    for alias in aliases:
        if alias == using:
            continue
        _replicate_one_delete(alias, pulp_id, attempts)


def reconcile_domains_to_alias(alias, dry_run=False):
    """
    Full reconciliation of every `Domain` row from `default` (authoritative) onto `alias`.

    Shared by the `sync-domains` management command (reconciling one or every satellite, as an
    explicit operator action or as part of `migrate-all`) and `_ensure_domains_replicated`
    (`apps.py`, a post_migrate hook that must guarantee `alias`'s `Domain` table is fully caught
    up *before* the same post_migrate wave's `_populate_artifact_serving_distribution`, KI-24,
    tries to create data-plane rows on `alias` that FK to it -- see the design doc's discussion
    of why `migrate --database=<satellite>` can't otherwise bootstrap a brand new satellite in a
    single pass). `alias` must already have a `core_domain` table matching the *current* `Domain`
    model's full schema (i.e. the whole `core` app already migrated on `alias`); raises
    `django.db.utils.DatabaseError` (uncaught) if it doesn't, since callers are expected to only
    invoke this once that precondition holds.

    Returns a `{"missing": set, "extra": set, "stale": set}` report of `pulp_id`s (always
    computed, even in `dry_run` mode; empty dict values mean no drift for that category).
    """
    from pulpcore.app.models import Domain

    default_domains = {domain.pulp_id: domain for domain in Domain.objects.using("default")}
    default_ids = set(default_domains)

    satellite_ids = set(Domain.objects.using(alias).values_list("pulp_id", flat=True))

    missing = default_ids - satellite_ids
    extra = satellite_ids - default_ids
    stale = set()
    for pulp_id in default_ids & satellite_ids:
        satellite_domain = Domain.objects.using(alias).get(pulp_id=pulp_id)
        if _comparable_domain_field_values(
            default_domains[pulp_id]
        ) != _comparable_domain_field_values(satellite_domain):
            stale.add(pulp_id)

    if dry_run:
        return {"missing": missing, "extra": extra, "stale": stale}

    for pulp_id in missing | stale:
        values = domain_field_values(default_domains[pulp_id])
        values.pop("pulp_id")
        try:
            instance = Domain.objects.using(alias).get(pulp_id=pulp_id)
            for key, value in values.items():
                setattr(instance, key, value)
        except Domain.DoesNotExist:
            instance = Domain(pulp_id=pulp_id, **values)
        # skip_hooks: this is a raw replica write of already-validated data (mirroring
        # _replicate_one_save), not a new domain-management action -- role creation/validation
        # hooks must not re-fire.
        instance.save(using=alias, skip_hooks=True)
    for pulp_id in extra:
        # `default` is authoritative: a Domain that no longer exists there was deleted, and its
        # replicated row on this satellite is orphaned.
        Domain.objects.using(alias).filter(pulp_id=pulp_id).delete()

    return {"missing": missing, "extra": extra, "stale": stale}


def _replicate_one_save(alias, pulp_id, defaults, attempts):
    from pulpcore.app.models import Domain

    delay = REPLICATION_RETRY_BACKOFF
    for attempt in range(1, attempts + 1):
        try:
            manager = Domain.objects.using(alias)
            try:
                instance = manager.get(pulp_id=pulp_id)
                for key, value in defaults.items():
                    setattr(instance, key, value)
            except Domain.DoesNotExist:
                instance = Domain(pulp_id=pulp_id, **defaults)
            # skip_hooks: this is a raw replica write of already-validated data, not a new
            # domain-management action -- role-creation / validation hooks must not re-fire.
            instance.save(using=alias, skip_hooks=True)
            return
        except Exception:
            logger.warning(
                "Domain replication to alias '%s' failed (attempt %d/%d) for domain %s.",
                alias,
                attempt,
                attempts,
                pulp_id,
                exc_info=True,
            )
            if attempt < attempts:
                time.sleep(delay)
                delay *= 2
    logger.error(
        "Domain replication to alias '%s' failed after %d attempts for domain %s. "
        "Run 'pulpcore-manager sync-domains' to reconcile.",
        alias,
        attempts,
        pulp_id,
    )


def _replicate_one_delete(alias, pulp_id, attempts):
    from pulpcore.app.models import Domain

    delay = REPLICATION_RETRY_BACKOFF
    for attempt in range(1, attempts + 1):
        try:
            Domain.objects.using(alias).filter(pulp_id=pulp_id).delete()
            return
        except Exception:
            logger.warning(
                "Domain delete-replication to alias '%s' failed (attempt %d/%d) for domain %s.",
                alias,
                attempt,
                attempts,
                pulp_id,
                exc_info=True,
            )
            if attempt < attempts:
                time.sleep(delay)
                delay *= 2
    logger.error(
        "Domain delete-replication to alias '%s' failed after %d attempts for domain %s. "
        "Run 'pulpcore-manager sync-domains' to reconcile.",
        alias,
        attempts,
        pulp_id,
    )


def on_domain_post_save(sender, instance, created, using, **kwargs):
    """`post_save` receiver for `Domain`. Connected in `apps.py`.

    Only replicates out from `default` (the authoritative alias). Writes performed by
    replication itself specify `using=<satellite alias>` explicitly, so this guard also
    prevents replication from re-triggering itself in a loop.
    """
    if using != "default":
        return
    replicate_domain_save(instance, using=using)


def on_domain_post_delete(sender, instance, using, **kwargs):
    """`post_delete` receiver for `Domain`. Connected in `apps.py`."""
    if using != "default":
        return
    replicate_domain_delete(instance.pulp_id, using=using)
