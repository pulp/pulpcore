"""
Replicates instance-wide RBAC identities (Users, Groups, Roles) to every satellite database
alias, mirroring pulpcore.app.domain_sync's approach for Domain.

UserRole/GroupRole grants are never replicated -- each one has exactly one home and is created
there directly (see pulpcore.app.role_util.assign_role):
  - a domain-wide grant lives on that domain's own alias, resolved explicitly
  - everything else -- object-level grants, and grants tied to neither an object nor a domain --
    just lives wherever the request creating it was already scoped (ambient routing)
A grant is only ever read back from the same alias it was written to (role_util.
get_objects_for_user_roles queries qs's own alias for all of them), so none of them need a copy
anywhere else. A grant with neither an object nor a domain is therefore scoped to whichever
database it was granted in, not to the whole Pulp instance -- a large tenant spanning multiple
satellites needs one such grant per satellite. Object-level grants are cleaned up automatically by
Django's native GenericRelation cascade (BaseModel.user_roles/group_roles) when their target is
deleted, the same as in a single-database Pulp instance.

User/Group/Role still need replicating because UserRole/GroupRole's user/group/role foreign keys
are real, DB-enforced constraints: whichever alias a grant lands on needs a local User/Group/Role
row for that constraint to validate.
"""

import logging
import time

from django.conf import settings
from django.contrib.auth import get_user_model

logger = logging.getLogger(__name__)

REPLICATION_RETRY_ATTEMPTS = 3
REPLICATION_RETRY_BACKOFF = 1


def satellite_aliases():
    return [alias for alias in settings.DATABASES if alias != "default"]


def _field_values(instance, exclude=()):
    return {
        field.attname: getattr(instance, field.attname)
        for field in instance._meta.concrete_fields
        if field.attname not in exclude
    }


def _permission_ids(permissions):
    # Permission/ContentType are provisioned identically (same code, same migrations, same
    # order) on every alias, so a Permission's pk on 'default' is trusted to be valid on every
    # satellite too -- consistent with how role_util.get_objects_for_user_roles resolves
    # Permission against 'default' and trusts it when filtering a query pinned to a satellite.
    return [p.pk for p in permissions]


def _set_permissions_on_alias(replica, alias, permission_ids):
    # Can't use replica.permissions.set(...) here: Permission is control-plane (see
    # db_router.CONTROL_PLANE_APPS), so the M2M manager always resolves the through table's write
    # alias to 'default' regardless of replica's own alias, silently never writing to the
    # satellite we're actually replicating to. Write the through table directly instead.
    field = type(replica)._meta.get_field("permissions")
    through = field.remote_field.through
    source_id = f"{field.m2m_field_name()}_id"
    target_id = f"{field.m2m_reverse_field_name()}_id"
    through.objects.using(alias).filter(**{source_id: replica.pk}).delete()
    through.objects.using(alias).bulk_create(
        [through(**{source_id: replica.pk, target_id: pid}) for pid in permission_ids]
    )


def _replicate_simple_save(model, alias, pk, values, attempts=REPLICATION_RETRY_ATTEMPTS):
    pk_field = model._meta.pk.attname
    delay = REPLICATION_RETRY_BACKOFF
    for attempt in range(1, attempts + 1):
        try:
            manager = model.objects.using(alias)
            try:
                instance = manager.get(**{pk_field: pk})
                for key, value in values.items():
                    setattr(instance, key, value)
            except model.DoesNotExist:
                instance = model(**{pk_field: pk}, **values)
            instance.save(using=alias)
            return instance
        except Exception:
            logger.warning(
                "Replicating %s(pk=%s) to alias '%s' failed (attempt %d/%d).",
                model.__name__,
                pk,
                alias,
                attempt,
                attempts,
                exc_info=True,
            )
            if attempt < attempts:
                time.sleep(delay)
                delay *= 2
    logger.error(
        "Replicating %s(pk=%s) to alias '%s' failed after %d attempts. Data on that alias "
        "referencing it may fail to validate until it is reconciled.",
        model.__name__,
        pk,
        alias,
        attempts,
    )
    return None


def _replicate_simple_delete(model, alias, pk, attempts=REPLICATION_RETRY_ATTEMPTS):
    pk_field = model._meta.pk.attname
    delay = REPLICATION_RETRY_BACKOFF
    for attempt in range(1, attempts + 1):
        try:
            model.objects.using(alias).filter(**{pk_field: pk}).delete()
            return
        except Exception:
            logger.warning(
                "Delete-replicating %s(pk=%s) to alias '%s' failed (attempt %d/%d).",
                model.__name__,
                pk,
                alias,
                attempt,
                attempts,
                exc_info=True,
            )
            if attempt < attempts:
                time.sleep(delay)
                delay *= 2
    logger.error(
        "Delete-replicating %s(pk=%s) to alias '%s' failed after %d attempts. A stale copy may "
        "remain there until it is reconciled.",
        model.__name__,
        pk,
        alias,
        attempts,
    )


def replicate_user(user, using=None, attempts=1):
    if using is not None and using != "default":
        return
    values = _field_values(user, exclude=("id",))
    for alias in satellite_aliases():
        _replicate_simple_save(type(user), alias, user.pk, values, attempts=attempts)


def remove_replicated_user(user, using=None, attempts=1):
    if using is not None and using != "default":
        return
    for alias in satellite_aliases():
        _replicate_simple_delete(type(user), alias, user.pk, attempts=attempts)


def replicate_group(group, using=None, attempts=1):
    if using is not None and using != "default":
        return
    values = _field_values(group, exclude=("id",))
    permission_ids = _permission_ids(group.permissions.all())
    for alias in satellite_aliases():
        replica = _replicate_simple_save(type(group), alias, group.pk, values, attempts=attempts)
        if replica is not None:
            _set_permissions_on_alias(replica, alias, permission_ids)


def remove_replicated_group(group, using=None, attempts=1):
    if using is not None and using != "default":
        return
    for alias in satellite_aliases():
        _replicate_simple_delete(type(group), alias, group.pk, attempts=attempts)


def replicate_role(role, using=None, attempts=1):
    if using is not None and using != "default":
        return
    values = _field_values(role, exclude=("pulp_id",))
    permission_ids = _permission_ids(role.permissions.all())
    for alias in satellite_aliases():
        replica = _replicate_simple_save(type(role), alias, role.pulp_id, values, attempts=attempts)
        if replica is not None:
            _set_permissions_on_alias(replica, alias, permission_ids)


def remove_replicated_role(role, using=None, attempts=1):
    if using is not None and using != "default":
        return
    for alias in satellite_aliases():
        _replicate_simple_delete(type(role), alias, role.pulp_id, attempts=attempts)


def ensure_replicated_on_alias(alias):
    """Backfill User/Group/Role rows onto a newly-migrated satellite alias, mirroring
    pulpcore.app.domain_sync.reconcile_domains_to_alias's role for Domain.

    Unlike the live on_*_post_save/delete signals below (which default to a single, fast attempt
    so a per-request database hiccup can't stall every User/Group/Role write), this is a one-shot
    bootstrap call made right after a satellite finishes migrating, so it's worth retrying with
    backoff instead of leaving the satellite permanently out of sync over one transient failure.
    """
    from pulpcore.app.models import Group
    from pulpcore.app.models.role import Role

    User = get_user_model()

    for user in User.objects.using("default").all():
        replicate_user(user, attempts=REPLICATION_RETRY_ATTEMPTS)
    for group in Group.objects.using("default").all():
        replicate_group(group, attempts=REPLICATION_RETRY_ATTEMPTS)
    for role in Role.objects.using("default").all():
        replicate_role(role, attempts=REPLICATION_RETRY_ATTEMPTS)


def on_user_post_save(sender, instance, using, **kwargs):
    replicate_user(instance, using=using)


def on_user_post_delete(sender, instance, using, **kwargs):
    remove_replicated_user(instance, using=using)


def on_group_post_save(sender, instance, using, **kwargs):
    replicate_group(instance, using=using)


def on_group_post_delete(sender, instance, using, **kwargs):
    remove_replicated_group(instance, using=using)


def on_role_post_save(sender, instance, using, **kwargs):
    replicate_role(instance, using=using)


def on_role_post_delete(sender, instance, using, **kwargs):
    remove_replicated_role(instance, using=using)
