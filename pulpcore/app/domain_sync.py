"""
Write-through replication of `Domain` rows to the satellite alias(es) that actually need them.

`Domain` is a control-plane model: it is authoritative on the `default` database alias, but
Postgres enforces foreign-key constraints locally, per physical database -- so any data-plane row
(`Repository`, `Content`, ...) written to a satellite alias needs a matching `Domain` row to
already exist *on that same alias*, or the FK insert fails outright. That's the only reason any
`Domain` row needs to exist off of `default` at all; nothing reads `Domain` cross-database
otherwise (the router, `for_each_domain()`, and `Domain.get_storage()` all resolve `Domain`
against `default`, never a satellite's copy).

Concretely, a given satellite alias only ever needs:

* The `default` domain's row, unconditionally -- `_populate_artifact_serving_distribution`
  (KI-24) is deliberately unguarded and runs on every alias during `migrate`, and the
  `ArtifactDistribution` row it creates there FKs to `pulp_domain` via `get_domain_pk()`, which
  outside any request/task context resolves to the `default` domain's id regardless of which
  alias is being migrated.
* Its own domain's row, for whichever domain is actually hosted there (`database_alias ==
  <this alias>`) -- needed for that domain's own `Repository`/`Content`/etc. rows.

Deliberately *not* "every `Domain` row on every alias": a satellite has no legitimate reason to
know about a domain it doesn't host -- doing so would leak every domain's name/storage
config/labels onto every satellite in the fleet. `move-domain` (`pulpcore.app.domain_move`) is
responsible for explicitly pushing a domain's row onto its destination alias *before* copying
that domain's data there (see `ensure_domain_on_alias`); replication here never proactively puts
a domain's row anywhere it isn't already the current host, "in case it moves there later."

Two mechanisms keep this in sync:

* `post_save`/`post_delete` signals (connected in `apps.py`) push individual changes as they
  happen, with retry + exponential backoff. Best-effort: a replication failure here is logged
  loudly but does not fail the triggering request/task.
* The `sync-domains` management command performs a full reconciliation pass, which is required
  to catch anything the signals miss (`bulk_create()`/`.update()` bypass Django signals
  entirely, a satellite that was down when a signal fired never gets the retried write once it
  comes back until reconciliation runs, and a domain that has since moved *away* from a satellite
  needs its now-stale row there pruned -- `reconcile_domains_to_alias`'s "extra" detection
  handles all three of these the same way).
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


def _target_aliases(domain):
    """
    Which satellite alias(es) `domain`'s row should be replicated to.

    The `default` domain belongs everywhere (see module docstring, KI-24); every other domain
    belongs only on its own current `database_alias` -- never proactively pushed anywhere else.
    A domain moving *to* a new alias is handled explicitly by `ensure_domain_on_alias`
    (`pulpcore.app.domain_move`), not by this ambient replication path.
    """
    if domain.name == "default":
        return satellite_aliases()
    if domain.database_alias in satellite_aliases():
        return [domain.database_alias]
    return []


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
    """Push a single Domain row to whichever satellite alias(es) it belongs on (see
    `_target_aliases`) -- write-through replication."""
    values = domain_field_values(domain)
    pulp_id = values.pop("pulp_id")
    for alias in _target_aliases(domain):
        if alias == using:
            continue
        _replicate_one_save(alias, pulp_id, values, attempts)


def replicate_domain_delete(domain, using=None, attempts=REPLICATION_RETRY_ATTEMPTS):
    """Delete a single Domain row from whichever satellite alias(es) it belongs on (see
    `_target_aliases`)."""
    for alias in _target_aliases(domain):
        if alias == using:
            continue
        _replicate_one_delete(alias, domain.pulp_id, attempts)


def ensure_domain_on_alias(domain, alias, attempts=REPLICATION_RETRY_ATTEMPTS):
    """
    Explicitly push `domain`'s row onto `alias`, regardless of `domain.database_alias`.

    Used by `move-domain` (`pulpcore.app.domain_move`) to seed the destination alias with the
    domain's row *before* `copy_domain_data` starts writing that domain's data-plane rows there
    (which FK to it) -- at that point `database_alias` still (correctly) points at the source
    alias, since it only flips at cutover, so the ambient `replicate_domain_save`/
    `_target_aliases` path (which only ever targets a domain's *current* alias) won't reach the
    destination on its own. Not used for anything else: ongoing replication is deliberately
    scoped to "current host only" (see module docstring) so a satellite never accumulates rows
    for domains it doesn't actually have data for.
    """
    values = domain_field_values(domain)
    pulp_id = values.pop("pulp_id")
    _replicate_one_save(alias, pulp_id, values, attempts)


def reconcile_domains_to_alias(alias, dry_run=False):
    """
    Full reconciliation of `alias`'s `Domain` rows against `default` (authoritative).

    Reconciles `alias` to hold exactly what it should (see module docstring): the `default`
    domain's row, plus a row for each domain whose `database_alias` is currently `alias`. Any
    other row found on `alias` -- including a domain that has since moved *away* from `alias`,
    or one that was deleted from `default` entirely -- is "extra" and gets pruned; this is the
    only mechanism that cleans up a domain's stale row after `move-domain` cuts it over
    elsewhere, so periodic/`migrate-all`-driven `sync-domains` runs matter even when nothing new
    was ever explicitly moved *to* `alias`.

    Shared by the `sync-domains` management command (reconciling one or every satellite, as an
    explicit operator action or as part of `migrate-all`) and `_ensure_domains_replicated`
    (`apps.py`, a post_migrate hook that must guarantee `alias`'s `Domain` table is fully caught
    up *before* the same post_migrate wave's `_populate_artifact_serving_distribution` tries to
    create data-plane rows on `alias` that FK to it -- `migrate --database=<satellite>` alone
    can't bootstrap a brand new satellite in a single pass, since the fixture/default-domain row
    those data-plane rows depend on isn't populated by `migrate` itself). `alias` must already
    have a `core_domain` table matching the *current* `Domain`
    model's full schema (i.e. the whole `core` app already migrated on `alias`); raises
    `django.db.utils.DatabaseError` (uncaught) if it doesn't, since callers are expected to only
    invoke this once that precondition holds.

    Returns a `{"missing": set, "extra": set, "stale": set}` report of `pulp_id`s (always
    computed, even in `dry_run` mode; empty dict values mean no drift for that category).
    """
    from pulpcore.app.models import Domain

    desired_domains = {
        domain.pulp_id: domain
        for domain in Domain.objects.using("default")
        if domain.name == "default" or domain.database_alias == alias
    }
    desired_ids = set(desired_domains)

    satellite_ids = set(Domain.objects.using(alias).values_list("pulp_id", flat=True))

    missing = desired_ids - satellite_ids
    extra = satellite_ids - desired_ids
    stale = set()
    for pulp_id in desired_ids & satellite_ids:
        satellite_domain = Domain.objects.using(alias).get(pulp_id=pulp_id)
        if _comparable_domain_field_values(
            desired_domains[pulp_id]
        ) != _comparable_domain_field_values(satellite_domain):
            stale.add(pulp_id)

    if dry_run:
        return {"missing": missing, "extra": extra, "stale": stale}

    for pulp_id in missing | stale:
        values = domain_field_values(desired_domains[pulp_id])
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
        # Either the domain no longer exists on `default` at all (deleted), or it does exist but
        # its `database_alias` no longer points at `alias` (moved elsewhere since this row was
        # last replicated here, e.g. by `move-domain`) -- either way `alias` has no legitimate
        # reason to still hold it, so prune it. This is the only cleanup path for the former
        # case; nothing else deletes a domain's row once it's moved away.
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
    replicate_domain_delete(instance, using=using)
