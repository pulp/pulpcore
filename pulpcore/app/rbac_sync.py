"""
Replicates instance-wide RBAC identities (Users, Groups, Roles) to every satellite database
alias, mirroring pulpcore.app.domain_sync's approach for Domain.

UserRole/GroupRole grants are never replicated: each lives on exactly one alias, decided at
creation (see role_util.assign_role), and is only ever read back from that same alias
(role_util.get_objects_for_user_roles), so no copy is needed elsewhere.

User/Group/Role still need replicating because UserRole/GroupRole's user/group/role foreign keys
are real, DB-enforced constraints: whichever alias a grant lands on needs a local row for that
constraint to validate.
"""

import logging
import time

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission

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


def _permission_natural_keys(permissions):
    # A Permission's pk isn't stable across aliases: it depends on each database's own migration
    # history (when a satellite was created, whether remove_stale_contenttypes has run there,
    # ...), which can differ from 'default'. (app_label, codename) is stable instead.
    return [
        (p.content_type.app_label, p.codename) for p in permissions.select_related("content_type")
    ]


def _permission_ids_by_natural_key(alias, natural_keys):
    rows = (
        Permission.objects.using(alias)
        .filter(content_type__app_label__in={key[0] for key in natural_keys})
        .values_list("content_type__app_label", "codename", "pk")
    )
    by_natural_key = {(app_label, codename): pk for app_label, codename, pk in rows}
    ids = []
    for key in natural_keys:
        pk = by_natural_key.get(key)
        if pk is None:
            logger.error(
                "No Permission matching app_label/codename %s on alias '%s'. This replicated "
                "grant will be missing that permission until the satellite is migrated and "
                "replication runs again.",
                key,
                alias,
            )
            continue
        ids.append(pk)
    return ids


def _set_permissions_on_alias(replica, alias, permission_natural_keys):
    # Can't use replica.permissions.set(...) here: Permission is control-plane (see
    # db_router.CONTROL_PLANE_APPS), so the M2M manager always resolves the through table's write
    # alias to 'default' regardless of replica's own alias, silently never writing to the
    # satellite we're actually replicating to. Write the through table directly instead.
    permission_ids = _permission_ids_by_natural_key(alias, permission_natural_keys)
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


def replicate_user(user, using=None, attempts=1, aliases=None):
    if using is not None and using != "default":
        return
    values = _field_values(user, exclude=("id",))
    for alias in aliases if aliases is not None else satellite_aliases():
        _replicate_simple_save(type(user), alias, user.pk, values, attempts=attempts)


def remove_replicated_user(user, using=None, attempts=1):
    if using is not None and using != "default":
        return
    for alias in satellite_aliases():
        _replicate_simple_delete(type(user), alias, user.pk, attempts=attempts)


def replicate_group(group, using=None, attempts=1, aliases=None):
    if using is not None and using != "default":
        return
    values = _field_values(group, exclude=("id",))
    permission_natural_keys = _permission_natural_keys(group.permissions.all())
    for alias in aliases if aliases is not None else satellite_aliases():
        replica = _replicate_simple_save(type(group), alias, group.pk, values, attempts=attempts)
        if replica is not None:
            _set_permissions_on_alias(replica, alias, permission_natural_keys)


def remove_replicated_group(group, using=None, attempts=1):
    if using is not None and using != "default":
        return
    for alias in satellite_aliases():
        _replicate_simple_delete(type(group), alias, group.pk, attempts=attempts)


def replicate_role(role, using=None, attempts=1, aliases=None):
    if using is not None and using != "default":
        return
    values = _field_values(role, exclude=("pulp_id",))
    permission_natural_keys = _permission_natural_keys(role.permissions.all())
    for alias in aliases if aliases is not None else satellite_aliases():
        replica = _replicate_simple_save(type(role), alias, role.pulp_id, values, attempts=attempts)
        if replica is not None:
            _set_permissions_on_alias(replica, alias, permission_natural_keys)


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
        replicate_user(user, attempts=REPLICATION_RETRY_ATTEMPTS, aliases=[alias])
    for group in Group.objects.using("default").all():
        replicate_group(group, attempts=REPLICATION_RETRY_ATTEMPTS, aliases=[alias])
    for role in Role.objects.using("default").all():
        replicate_role(role, attempts=REPLICATION_RETRY_ATTEMPTS, aliases=[alias])


def on_user_post_save(sender, instance, using, update_fields=None, **kwargs):
    # update_last_login() saves with update_fields=["last_login"] on every login. Replicating
    # that synchronously to every satellite would make login latency scale with satellite count,
    # and a slow/unavailable satellite would delay every login -- nothing a satellite needs
    # last_login for, so skip replication when it's the only thing that changed.
    if update_fields is not None and set(update_fields) <= {"last_login"}:
        return
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


def on_group_permissions_changed(sender, instance, action, reverse, using, **kwargs):
    # Group.permissions is an M2M: .set()/.add()/.remove()/.clear() change membership without
    # saving the Group row, so on_group_post_save's post_save hook never fires for them. `reverse`
    # is True for changes from the Permission side, which Pulp doesn't do and has nothing to
    # replicate for anyway (Permission is control-plane).
    if reverse or action not in ("post_add", "post_remove", "post_clear"):
        return
    replicate_group(instance, using=using)


def on_role_permissions_changed(sender, instance, action, reverse, using, **kwargs):
    """Role.permissions counterpart to on_group_permissions_changed -- same M2M-bypasses-
    post_save gap, same fix."""
    if reverse or action not in ("post_add", "post_remove", "post_clear"):
        return
    replicate_role(instance, using=using)
