"""
Replicates a ContentGuard -- and, if it's a CompositeContentGuard, its child guards and guard
membership -- from whatever alias it actually lives on into 'default'.

This exists because Domain.default_content_guard is a real, DB-enforced foreign key, and Domain
rows always live in 'default' (see db_router.CONTROL_PLANE_LABELS). Postgres has no cross-database
foreign keys, so pointing it at a ContentGuard that only exists on a satellite alias would violate
that constraint the moment the Domain row is written. Giving 'default' its own local copy of the
guard -- same pulp_id, same owning domain -- lets the FK validate without a cross-database
relationship.

Unlike pulpcore.app.rbac_sync (every alias gets an always-current copy of every User/Group/Role)
or pulpcore.app.domain_sync (every satellite gets a copy of every Domain routed to it), this is
narrow and on-demand: only content guards actually assigned as some domain's default_content_guard
get a 'default' replica, created at assignment time (see the default_content_guard hook on
pulpcore.app.models.domain.Domain) and kept in sync afterwards by the ContentGuard AFTER_SAVE/
AFTER_DELETE hooks below -- which only act on a guard that already has a 'default' replica, so a
guard nobody ever assigned as a default_content_guard pays no replication cost at all.
"""

import logging
import time

logger = logging.getLogger(__name__)

REPLICATION_RETRY_ATTEMPTS = 3
REPLICATION_RETRY_BACKOFF = 1


def _field_values(instance, exclude=()):
    return {
        field.attname: getattr(instance, field.attname)
        for field in instance._meta.concrete_fields
        if field.attname not in exclude
    }


def _cast_on_own_alias(guard):
    """guard.cast(), but resolved on guard's own alias instead of ambient context.

    MasterModel.cast() always queries via the plain default manager with no .using(), which
    would look for the concrete-subclass row wherever ambient routing happens to point instead
    of wherever `guard` itself actually lives -- the wrong thing here, since this module is
    specifically dealing with guards living on a different alias than the request's ambient one.
    """
    if guard.pulp_type == guard.get_pulp_type():
        return guard
    model = guard._pulp_model_map[guard.pulp_type]
    return model.objects.using(guard._state.db).get(pk=guard.pk)


def _replicate_one_save(model, pk, values, attempts=REPLICATION_RETRY_ATTEMPTS):
    pk_field = model._meta.pk.attname
    delay = REPLICATION_RETRY_BACKOFF
    for attempt in range(1, attempts + 1):
        try:
            manager = model.objects.using("default")
            try:
                instance = manager.get(**{pk_field: pk})
                for key, value in values.items():
                    setattr(instance, key, value)
            except model.DoesNotExist:
                instance = model(**{pk_field: pk}, **values)
            instance.save(using="default")
            return instance
        except Exception:
            logger.warning(
                "Replicating %s(pk=%s) to 'default' failed (attempt %d/%d).",
                model.__name__,
                pk,
                attempt,
                attempts,
                exc_info=True,
            )
            if attempt < attempts:
                time.sleep(delay)
                delay *= 2
    logger.error(
        "Replicating %s(pk=%s) to 'default' failed after %d attempts. Domain."
        "default_content_guard referencing it may fail to validate until it is reconciled.",
        model.__name__,
        pk,
        attempts,
    )
    return None


def _set_guard_membership_on_default(replica, child_pks):
    # replica.guards.set(...) would resolve the through table's write alias via the router based
    # on ContentGuard (a data-plane model) -- ambient, not necessarily 'default' -- so write the
    # through table directly instead, mirroring rbac_sync._set_permissions_on_alias.
    field = type(replica)._meta.get_field("guards")
    through = field.remote_field.through
    source_id = f"{field.m2m_field_name()}_id"
    target_id = f"{field.m2m_reverse_field_name()}_id"
    through.objects.using("default").filter(**{source_id: replica.pk}).delete()
    through.objects.using("default").bulk_create(
        [through(**{source_id: replica.pk, target_id: pk}) for pk in child_pks]
    )


def replicate_content_guard_to_default(guard, attempts=REPLICATION_RETRY_ATTEMPTS):
    """
    Replicate ``guard`` -- resolved to its concrete subclass -- into 'default', recursing into
    its child guards and 'guards' membership first if it's a CompositeContentGuard.

    No-ops if ``guard`` already lives in 'default' (the common case: a content guard lives in
    'default' unless its owning domain is mapped to a satellite alias).
    """
    guard = _cast_on_own_alias(guard)
    if guard._state.db == "default":
        return

    from pulpcore.app.models import CompositeContentGuard

    children = None
    if isinstance(guard, CompositeContentGuard):
        children = list(guard.guards.all())
        for child in children:
            replicate_content_guard_to_default(child, attempts=attempts)

    values = _field_values(guard, exclude=(guard._meta.pk.attname,))
    replica = _replicate_one_save(type(guard), guard.pk, values, attempts=attempts)

    if replica is not None and children is not None:
        _set_guard_membership_on_default(replica, [child.pk for child in children])


def remove_content_guard_default_replica(pk, attempts=REPLICATION_RETRY_ATTEMPTS):
    from pulpcore.app.contexts import with_domain
    from pulpcore.app.models import ContentGuard, Domain

    delay = REPLICATION_RETRY_BACKOFF
    for attempt in range(1, attempts + 1):
        try:
            # Deleting a MasterModel detail row (e.g. HeaderContentGuard) is a multi-table
            # cascade: Django's collector re-queries the concrete-subclass table to find the
            # matching child row, sometimes with a restricted field set. If ambient context
            # doesn't already agree with 'default' here, MasterModel.__init__ handling a
            # deferred field on that re-fetched row falls back to ambient routing instead of
            # 'default', misses, and raises DoesNotExist. Pin ambient context to 'default' for
            # the duration of the delete so that can't happen, regardless of caller context.
            with with_domain(Domain.objects.get(name="default")):
                ContentGuard.objects.using("default").filter(pk=pk).delete()
            return
        except Exception:
            logger.warning(
                "Delete-replicating ContentGuard(pk=%s) from 'default' failed (attempt %d/%d).",
                pk,
                attempt,
                attempts,
                exc_info=True,
            )
            if attempt < attempts:
                time.sleep(delay)
                delay *= 2
    logger.error(
        "Delete-replicating ContentGuard(pk=%s) from 'default' failed after %d attempts. A "
        "stale replica may remain there until it is reconciled.",
        pk,
        attempts,
    )


def on_content_guard_saved(guard):
    """AFTER_SAVE hook body for ContentGuard (see models.publication.ContentGuard). Only acts on
    a guard that already has a 'default' replica -- i.e. one some domain's default_content_guard
    currently points at -- so saving a guard nobody uses as a default_content_guard costs nothing
    beyond this one existence check."""
    from pulpcore.app.models import ContentGuard

    if guard._state.db == "default":
        return
    if not ContentGuard.objects.using("default").filter(pk=guard.pk).exists():
        return
    replicate_content_guard_to_default(guard, attempts=1)


def on_content_guard_deleted(guard):
    """AFTER_DELETE hook body for ContentGuard. See on_content_guard_saved."""
    from pulpcore.app.models import ContentGuard

    if guard._state.db == "default":
        return
    if not ContentGuard.objects.using("default").filter(pk=guard.pk).exists():
        return
    remove_content_guard_default_replica(guard.pk, attempts=1)
