import logging
import time

from django.conf import settings

logger = logging.getLogger(__name__)

REPLICATION_RETRY_ATTEMPTS = 3
REPLICATION_RETRY_BACKOFF = 1


def satellite_aliases():
    return [alias for alias in settings.DATABASES if alias != "default"]


def _target_aliases(domain):
    if domain.name == "default":
        return satellite_aliases()
    if domain.database_alias in satellite_aliases():
        return [domain.database_alias]
    return []


def domain_field_values(domain):
    return {field.attname: getattr(domain, field.attname) for field in domain._meta.concrete_fields}


def _comparable_domain_field_values(domain):
    values = domain_field_values(domain)
    values.pop("pulp_last_updated", None)
    return values


def replicate_domain_save(domain, using=None, attempts=REPLICATION_RETRY_ATTEMPTS):
    values = domain_field_values(domain)
    pulp_id = values.pop("pulp_id")
    for alias in _target_aliases(domain):
        if alias == using:
            continue
        _replicate_one_save(alias, pulp_id, values, attempts)


def replicate_domain_delete(domain, using=None, attempts=REPLICATION_RETRY_ATTEMPTS):
    for alias in _target_aliases(domain):
        if alias == using:
            continue
        _replicate_one_delete(alias, domain.pulp_id, attempts)


def ensure_domain_on_alias(domain, alias, attempts=REPLICATION_RETRY_ATTEMPTS):
    values = domain_field_values(domain)
    pulp_id = values.pop("pulp_id")
    _replicate_one_save(alias, pulp_id, values, attempts)


def reconcile_domains_to_alias(alias, dry_run=False):
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
        instance.save(using=alias, skip_hooks=True)
    for pulp_id in extra:
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
    if using != "default":
        return
    replicate_domain_save(instance, using=using)


def on_domain_post_delete(sender, instance, using, **kwargs):
    if using != "default":
        return
    replicate_domain_delete(instance, using=using)
