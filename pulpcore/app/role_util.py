from collections import defaultdict
from functools import lru_cache
from gettext import gettext as _

from django.conf import settings
from django.contrib.auth import get_user_model as django_get_user_model
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import BadRequest
from django.db import router
from django.db.models import CharField, Q
from django.db.models.functions import Cast

from pulpcore.app.models import Group
from pulpcore.app.models.role import GroupRole, Role, UserRole


@lru_cache(maxsize=1)
def get_user_model():
    return django_get_user_model()


def grant_alias(obj=None, domain=None):
    if domain is not None:
        return domain.database_alias
    if obj is not None:
        return obj._state.db
    return router.db_for_read(Role)


def assign_role(rolename, entity, obj=None, domain=None):
    """
    Assign a role to a user or a group.

    Args:
        rolename (str): Name of the role to assign.
        entity (django.contrib.auth.User or pulpcore.app.models.Group): Entity to gain the role.
        obj (Optional[pulpcore.app.models.BaseModel]): Object the role permisssions are to be
            asserted on.
        domain (Optional[pulpcore.app.models.Domain]): Domain the role permissions are to be
            asserted on. Mutually exclusive with obj.
    """
    if obj and domain:
        raise BadRequest(_("Object and domain can not both be set."))
    using = grant_alias(obj, domain)
    try:
        role = Role.objects.using(using).get(name=rolename)
    except Role.DoesNotExist:
        raise BadRequest(_("The role '{}' does not exist.").format(rolename))
    if obj is not None:
        ctype = ContentType.objects.db_manager(using).get_for_model(obj, for_concrete_model=False)
        if not role.permissions.filter(content_type__pk=ctype.id).exists():
            raise BadRequest(
                _("The role '{}' does not carry any permission for that object.").format(rolename)
            )
    if domain is not None:
        # Check that at least one permission is on a model with a domain
        for permission in role.permissions.all():
            model = permission.content_type.model_class()
            if hasattr(model, "pulp_domain"):
                break
        else:
            raise BadRequest(
                _("The role '{}' does not carry any permission on an object with a domain").format(
                    rolename
                )
            )
    if isinstance(entity, Group):
        return GroupRole.objects.using(using).create(
            role=role, group=entity, content_object=obj, domain=domain
        )
    else:
        return UserRole.objects.using(using).create(
            role=role, user=entity, content_object=obj, domain=domain
        )


def remove_role(rolename, entity, obj=None, domain=None):
    """
    Remove a role from a user or a group.

    Args:
        rolename (str): Name of the role to assign.
        entity (django.contrib.auth.User or pulpcore.app.models.Group): Entity to lose the role.
        obj (Optional[pulpcore.app.models.BaseModel]): Object the role permisssions are to be
            asserted on.
        domain (Optional[pulpcore.app.models.Domain]): Domain the role permissions are to be
            asserted on. Mutually exclusive with obj.
    """
    if obj and domain:
        raise BadRequest(_("Object and domain can not both be set."))
    using = grant_alias(obj, domain)
    try:
        role = Role.objects.using(using).get(name=rolename)
    except Role.DoesNotExist:
        raise BadRequest(_("The role '{}' does not exist.").format(rolename))
    if isinstance(entity, Group):
        qs = GroupRole.objects.using(using).filter(role=role, group=entity)
    else:
        qs = UserRole.objects.using(using).filter(role=role, user=entity)
    if obj is None:
        # Global or domain search
        qs = qs.filter(object_id=None, domain=domain)
    else:
        ctype = ContentType.objects.db_manager(using).get_for_model(obj, for_concrete_model=False)
        qs = qs.filter(content_type__pk=ctype.id, object_id=obj.pk)
    qs.delete()


def get_perms_for_model(obj):
    alias = getattr(getattr(obj, "_state", None), "db", None) or grant_alias()
    ctype = ContentType.objects.db_manager(alias).get_for_model(obj, for_concrete_model=False)
    return Permission.objects.using(alias).filter(content_type__pk=ctype.id)


def _get_permission(alias, permission_name):
    permissions = Permission.objects.using(alias)
    if "." in permission_name:
        app_label, codename = permission_name.split(".", maxsplit=1)
        return permissions.get(content_type__app_label=app_label, codename=codename)
    return permissions.get(codename=permission_name)


def _domain_grant_aliases(qs):
    # Domain grants live in their domain's database, which for control-plane models (e.g. Task)
    # differs from the queryset's own database.
    from pulpcore.app.db_router import PulpDomainRouter, is_multi_db_routing_active

    if is_multi_db_routing_active() and PulpDomainRouter()._is_control_plane(qs.model):
        return list(settings.DATABASES)
    return [qs.db]


def _domain_grant_ids(user, group_ids, permission_name, permission, alias, domain=None):
    """Domain ids on `alias` where the user (directly or via `group_ids`) holds the permission.

    `permission` is reused when it was already resolved on `alias`.
    """
    if permission._state.db != alias:
        try:
            permission = _get_permission(alias, permission_name)
        except Permission.DoesNotExist:
            return []
    filters = {"role__permissions": permission}
    if domain is None:
        filters["domain__isnull"] = False
    else:
        filters["domain"] = domain
    ids = list(
        UserRole.objects.using(alias)
        .filter(user=user, **filters)
        .values_list("domain_id", flat=True)
    )
    if group_ids:
        ids.extend(
            GroupRole.objects.using(alias)
            .filter(group_id__in=group_ids, **filters)
            .values_list("domain_id", flat=True)
        )
    return ids


def get_objects_for_user_roles(
    user,
    permission_name,
    qs,
    use_groups=True,
    with_superuser=True,
    accept_domain_perms=True,
    accept_global_perms=True,
):
    if not user.is_authenticated:
        return qs.none()
    if with_superuser and user.is_superuser:
        return qs

    alias = qs.db
    permission = _get_permission(alias, permission_name)

    group_ids = list(user.groups.values_list("pk", flat=True)) if use_groups else []

    if accept_global_perms:
        if (
            UserRole.objects.using(alias)
            .filter(user=user, object_id=None, domain=None, role__permissions=permission)
            .exists()
        ):
            return qs
        if (
            use_groups
            and GroupRole.objects.using(alias)
            .filter(
                group_id__in=group_ids,
                object_id=None,
                domain=None,
                role__permissions=permission,
            )
            .exists()
        ):
            return qs

    user_role_pks = (
        UserRole.objects.using(alias)
        .filter(user=user, domain__isnull=True, role__permissions=permission)
        .values_list("object_id", flat=True)
    )
    final_q = Q(pk_str__in=user_role_pks)
    if accept_domain_perms and hasattr(qs.model, "pulp_domain"):
        # Optimization used by get_queryset in NamedModelViewSet
        if filtered_domain := getattr(qs, "filtered_domain", None):
            if _domain_grant_ids(
                user,
                group_ids,
                permission_name,
                permission,
                filtered_domain.database_alias,
                filtered_domain,
            ):
                return qs
        else:
            domains = []
            for domain_alias in _domain_grant_aliases(qs):
                domains.extend(
                    _domain_grant_ids(user, group_ids, permission_name, permission, domain_alias)
                )
            final_q |= Q(pulp_domain_id__in=domains)

    if use_groups:
        group_role_pks = (
            GroupRole.objects.using(alias)
            .filter(group_id__in=group_ids, role__permissions=permission, domain__isnull=True)
            .values_list("object_id", flat=True)
        )
        final_q |= Q(pk_str__in=group_role_pks)

    return qs.annotate(pk_str=Cast("pk", output_field=CharField())).filter(final_q)


def get_objects_for_user(
    user,
    perms,
    qs,
    use_groups=True,
    any_perm=False,
    with_superuser=True,
    accept_domain_perms=True,
    accept_global_perms=True,
):
    if (
        "pulpcore.app.workload_identity.backend.WorkloadIdentityBackend"
        in settings.AUTHENTICATION_BACKENDS
    ):
        from pulpcore.app.workload_identity.principal import WorkloadIdentityPrincipal

        if isinstance(user, WorkloadIdentityPrincipal):
            from pulpcore.app.workload_identity.authz import grants_queryset

            grants = user.grants
            if isinstance(perms, str):
                return grants_queryset(grants, perms, qs)
            if any_perm:
                result = qs.none()
                for permission_name in perms:
                    result |= grants_queryset(grants, permission_name, qs)
                return result
            result = qs.all()
            for permission_name in perms:
                result &= grants_queryset(grants, permission_name, qs)
            return result

    new_qs = qs.none()
    replace = False
    if "pulpcore.backends.ObjectRolePermissionBackend" in settings.AUTHENTICATION_BACKENDS:
        if isinstance(perms, str):
            permission_name = perms
            new_qs |= get_objects_for_user_roles(
                user,
                permission_name,
                qs=qs,
                use_groups=use_groups,
                with_superuser=with_superuser,
                accept_domain_perms=accept_domain_perms,
                accept_global_perms=accept_global_perms,
            )
        else:
            # Emulate multiple permissions and `any_perm`
            if any_perm:
                aggregate_qs = qs.none()
                for permission_name in perms:
                    aggregate_qs |= get_objects_for_user_roles(
                        user,
                        permission_name,
                        qs=qs,
                        use_groups=use_groups,
                        with_superuser=with_superuser,
                        accept_domain_perms=accept_domain_perms,
                        accept_global_perms=accept_global_perms,
                    )
            else:
                aggregate_qs = qs.all()
                for permission_name in perms:
                    aggregate_qs &= get_objects_for_user_roles(
                        user,
                        permission_name,
                        qs=qs,
                        use_groups=use_groups,
                        with_superuser=with_superuser,
                        accept_domain_perms=accept_domain_perms,
                        accept_global_perms=accept_global_perms,
                    )
            new_qs |= aggregate_qs
        replace = True
    if replace:
        qs = new_qs
    return qs


def get_objects_for_group_roles(
    group, permission_name, qs, accept_domain_perms=True, accept_global_perms=True
):
    alias = qs.db
    grants = GroupRole.objects.using(alias).filter(group=group)
    if "." in permission_name:
        app_label, codename = permission_name.split(".", maxsplit=1)
        permission = Permission.objects.using(alias).get(
            content_type__app_label=app_label, codename=codename
        )
    else:
        permission = Permission.objects.using(alias).get(codename=permission_name)

    if (
        accept_global_perms
        and grants.filter(
            object_id=None, domain_id__isnull=True, role__permissions=permission
        ).exists()
    ):
        return qs

    group_role_pks = grants.filter(
        domain_id__isnull=True, role__permissions=permission
    ).values_list("object_id", flat=True)
    final_q = Q(pk_str__in=group_role_pks)
    if accept_domain_perms and hasattr(qs.model, "pulp_domain"):
        domains = grants.filter(domain__isnull=False, role__permissions=permission).values_list(
            "domain_id", flat=True
        )
        final_q |= Q(pulp_domain_id__in=domains)

    return qs.annotate(pk_str=Cast("pk", output_field=CharField())).filter(final_q)


def get_objects_for_group(
    group, perms, qs, any_perm=False, accept_domain_perms=True, accept_global_perms=True
):
    new_qs = qs.none()
    replace = False
    if "pulpcore.backends.ObjectRolePermissionBackend" in settings.AUTHENTICATION_BACKENDS:
        if isinstance(perms, str):
            permission_name = perms
            new_qs |= get_objects_for_group_roles(
                group,
                permission_name,
                qs=qs,
                accept_domain_perms=accept_domain_perms,
                accept_global_perms=accept_global_perms,
            )
        else:
            # Emulate multiple permissions and `any_perm`
            if any_perm:
                aggregate_qs = qs.none()
                for permission_name in perms:
                    aggregate_qs |= get_objects_for_group_roles(
                        group,
                        permission_name,
                        qs=qs,
                        accept_domain_perms=accept_domain_perms,
                        accept_global_perms=accept_global_perms,
                    )
            else:
                aggregate_qs = qs.all()
                for permission_name in perms:
                    aggregate_qs &= get_objects_for_group_roles(
                        group,
                        permission_name,
                        qs=qs,
                        accept_domain_perms=accept_domain_perms,
                        accept_global_perms=accept_global_perms,
                    )
            new_qs |= aggregate_qs
        replace = True
    if replace:
        qs = new_qs
    return qs


def get_users_with_perms_roles(
    obj,
    with_superusers=False,
    with_group_users=True,
    only_with_perms_in=None,
    include_domain_permissions=True,
    include_model_permissions=True,
    for_concrete_model=False,
):
    User = get_user_model()
    qs = User.objects.none()
    if with_superusers:
        qs |= User.objects.filter(is_superuser=True)
    alias = obj._state.db
    ctype = ContentType.objects.db_manager(alias).get_for_model(
        obj, for_concrete_model=for_concrete_model
    )
    perms = Permission.objects.using(alias).filter(content_type__pk=ctype.id)
    if only_with_perms_in:
        codenames = [
            split_perm[-1]
            for split_perm in (perm.split(".", maxsplit=1) for perm in only_with_perms_in)
            if len(split_perm) == 1 or split_perm[0] == ctype.app_label
        ]
        perms = perms.filter(codename__in=codenames)

    object_query = Q(content_type=ctype, object_id=obj.pk)
    if include_domain_permissions and getattr(obj, "pulp_domain", None):
        object_query = Q(domain=obj.pulp_domain_id) | object_query
    if include_model_permissions:
        object_query = Q(object_id=None, domain__isnull=True) | object_query

    user_roles = (
        UserRole.objects.using(alias).filter(role__permissions__in=perms).filter(object_query)
    )
    qs |= User.objects.filter(pk__in=list(user_roles.values_list("user_id", flat=True)))
    if with_group_users:
        # Maybe I'm missing something, but I think this should have been using object_query
        group_roles = (
            GroupRole.objects.using(alias).filter(role__permissions__in=perms).filter(object_query)
        )
        groups = list(group_roles.values_list("group_id", flat=True))
        qs |= User.objects.filter(groups__in=groups)
    return qs.distinct()


def get_users_with_perms_attached_perms(
    obj,
    with_superusers=False,
    with_group_users=True,
    only_with_perms_in=None,
    include_domain_permissions=True,
    include_model_permissions=True,
    for_concrete_model=False,
):
    User = get_user_model()
    alias = obj._state.db
    ctype = ContentType.objects.db_manager(alias).get_for_model(
        obj, for_concrete_model=for_concrete_model
    )
    perms = Permission.objects.using(alias).filter(content_type__pk=ctype.id)
    if only_with_perms_in:
        codenames = [
            split_perm[-1]
            for split_perm in (perm.split(".", maxsplit=1) for perm in only_with_perms_in)
            if len(split_perm) == 1 or split_perm[0] == ctype.app_label
        ]
        perms = perms.filter(codename__in=codenames)

    object_query = Q(content_type=ctype, object_id=obj.pk)
    if include_domain_permissions and getattr(obj, "pulp_domain", None):
        object_query = Q(domain=obj.pulp_domain_id) | object_query
    if include_model_permissions:
        object_query = Q(object_id=None) | object_query

    user_roles = (
        UserRole.objects.using(alias).filter(role__permissions__in=perms).filter(object_query)
    )
    res = defaultdict(set)
    if with_superusers:
        for user in User.objects.filter(is_superuser=True):
            res[user].update(perms)
    for user_role in user_roles:
        res[user_role.user].update(
            user_role.role.permissions.using(alias)
            .filter(pk__in=perms)
            .values_list("codename", flat=True)
        )
    if with_group_users:
        group_roles = (
            GroupRole.objects.using(alias).filter(role__permissions__in=perms).filter(object_query)
        )
        for group_role in group_roles:
            for user in group_role.group.user_set.all():
                res[user].update(
                    group_role.role.permissions.using(alias)
                    .filter(pk__in=perms)
                    .values_list("codename", flat=True)
                )
    return {k: list(v) for k, v in res.items()}


def get_users_with_perms_attached_roles(
    obj,
    with_group_users=True,
    only_with_perms_in=None,
    include_domain_permissions=True,
    include_model_permissions=True,
    for_concrete_model=False,
):
    alias = obj._state.db
    ctype = ContentType.objects.db_manager(alias).get_for_model(
        obj, for_concrete_model=for_concrete_model
    )
    perms = Permission.objects.using(alias).filter(content_type__pk=ctype.id)
    if only_with_perms_in:
        codenames = [
            split_perm[-1]
            for split_perm in (perm.split(".", maxsplit=1) for perm in only_with_perms_in)
            if len(split_perm) == 1 or split_perm[0] == ctype.app_label
        ]
        perms = perms.filter(codename__in=codenames)

    object_query = Q(content_type=ctype, object_id=obj.pk)
    if include_domain_permissions and getattr(obj, "pulp_domain", None):
        object_query = Q(domain=obj.pulp_domain_id) | object_query
    if include_model_permissions:
        object_query = Q(object_id=None) | object_query

    user_roles = (
        UserRole.objects.using(alias).filter(role__permissions__in=perms).filter(object_query)
    )
    res = defaultdict(set)
    for user_role in user_roles:
        res[user_role.user].add(user_role.role.name)
    if with_group_users:
        group_roles = (
            GroupRole.objects.using(alias).filter(role__permissions__in=perms).filter(object_query)
        )
        for group_role in group_roles:
            for user in group_role.group.user_set.all():
                res[user].add(group_role.role.name)
    return {k: list(v) for k, v in res.items()}


# Interface copied from django guardian
def get_users_with_perms(
    obj,
    attach_perms=False,
    with_superusers=False,
    with_group_users=True,
    only_with_perms_in=None,
    include_domain_permissions=True,
    include_model_permissions=True,
    for_concrete_model=False,
):
    User = get_user_model()
    if attach_perms:
        res = defaultdict(set)
        if "pulpcore.backends.ObjectRolePermissionBackend" in settings.AUTHENTICATION_BACKENDS:
            for key, value in get_users_with_perms_attached_perms(
                obj,
                with_superusers=with_superusers,
                with_group_users=with_group_users,
                only_with_perms_in=only_with_perms_in,
                include_domain_permissions=include_domain_permissions,
                include_model_permissions=include_model_permissions,
                for_concrete_model=for_concrete_model,
            ).items():
                res[key].update(value)
        return {k: list(v) for k, v in res.items()}
    qs = User.objects.none()
    if "pulpcore.backends.ObjectRolePermissionBackend" in settings.AUTHENTICATION_BACKENDS:
        qs |= get_users_with_perms_roles(
            obj,
            with_superusers=with_superusers,
            with_group_users=with_group_users,
            only_with_perms_in=only_with_perms_in,
            include_domain_permissions=include_domain_permissions,
            include_model_permissions=include_model_permissions,
            for_concrete_model=for_concrete_model,
        )
    return qs.distinct()


def get_groups_with_perms_roles(
    obj,
    only_with_perms_in=None,
    include_domain_permissions=True,
    include_model_permissions=True,
    for_concrete_model=False,
):
    alias = obj._state.db
    ctype = ContentType.objects.db_manager(alias).get_for_model(
        obj, for_concrete_model=for_concrete_model
    )
    perms = Permission.objects.using(alias).filter(content_type__pk=ctype.id)
    if only_with_perms_in:
        codenames = [
            split_perm[-1]
            for split_perm in (perm.split(".", maxsplit=1) for perm in only_with_perms_in)
            if len(split_perm) == 1 or split_perm[0] == ctype.app_label
        ]
        perms = perms.filter(codename__in=codenames)

    object_query = Q(content_type=ctype, object_id=obj.pk)
    if include_domain_permissions and getattr(obj, "pulp_domain", None):
        object_query = Q(domain=obj.pulp_domain_id) | object_query
    if include_model_permissions:
        object_query = Q(object_id=None) | object_query

    group_roles = (
        GroupRole.objects.using(alias).filter(role__permissions__in=perms).filter(object_query)
    )
    qs = Group.objects.filter(
        pk__in=list(group_roles.values_list("group_id", flat=True))
    ).distinct()
    return qs


def get_groups_with_perms_attached_perms(
    obj,
    only_with_perms_in=None,
    include_domain_permissions=True,
    include_model_permissions=True,
    for_concrete_model=False,
):
    alias = obj._state.db
    ctype = ContentType.objects.db_manager(alias).get_for_model(
        obj, for_concrete_model=for_concrete_model
    )
    perms = Permission.objects.using(alias).filter(content_type__pk=ctype.id)
    if only_with_perms_in:
        codenames = [
            split_perm[-1]
            for split_perm in (perm.split(".", maxsplit=1) for perm in only_with_perms_in)
            if len(split_perm) == 1 or split_perm[0] == ctype.app_label
        ]
        perms = perms.filter(codename__in=codenames)

    object_query = Q(content_type=ctype, object_id=obj.pk)
    if include_domain_permissions and getattr(obj, "pulp_domain", None):
        object_query = Q(domain=obj.pulp_domain) | object_query
    if include_model_permissions:
        object_query = Q(object_id=None) | object_query

    group_roles = (
        GroupRole.objects.using(alias).filter(role__permissions__in=perms).filter(object_query)
    )
    res = defaultdict(set)
    for group_role in group_roles:
        res[group_role.group].update(
            group_role.role.permissions.using(alias)
            .filter(pk__in=perms)
            .values_list("codename", flat=True)
        )
    return {k: list(v) for k, v in res.items()}


def get_groups_with_perms_attached_roles(
    obj,
    only_with_perms_in=None,
    include_domain_permissions=True,
    include_model_permissions=True,
    for_concrete_model=False,
):
    alias = obj._state.db
    ctype = ContentType.objects.db_manager(alias).get_for_model(
        obj, for_concrete_model=for_concrete_model
    )
    perms = Permission.objects.using(alias).filter(content_type__pk=ctype.id)
    if only_with_perms_in:
        codenames = [
            split_perm[-1]
            for split_perm in (perm.split(".", maxsplit=1) for perm in only_with_perms_in)
            if len(split_perm) == 1 or split_perm[0] == ctype.app_label
        ]
        perms = perms.filter(codename__in=codenames)

    object_query = Q(content_type=ctype, object_id=obj.pk)
    if include_domain_permissions and getattr(obj, "pulp_domain", None):
        object_query = Q(domain=obj.pulp_domain_id) | object_query
    if include_model_permissions:
        object_query = Q(object_id=None) | object_query

    group_roles = (
        GroupRole.objects.using(alias).filter(role__permissions__in=perms).filter(object_query)
    )
    res = defaultdict(set)
    for group_role in group_roles:
        res[group_role.group].add(group_role.role.name)
    return {k: list(v) for k, v in res.items()}


# Interface copied from django guardian
def get_groups_with_perms(
    obj,
    attach_perms=False,
    include_domain_permissions=True,
    include_model_permissions=True,
    for_concrete_model=False,
):
    if attach_perms:
        res = defaultdict(set)
        if "pulpcore.backends.ObjectRolePermissionBackend" in settings.AUTHENTICATION_BACKENDS:
            for key, value in get_groups_with_perms_attached_perms(
                obj,
                include_domain_permissions=include_domain_permissions,
                include_model_permissions=include_model_permissions,
                for_concrete_model=for_concrete_model,
            ).items():
                res[key].update(value)
        return {k: list(v) for k, v in res.items()}
    else:
        qs = Group.objects.none()
        if "pulpcore.backends.ObjectRolePermissionBackend" in settings.AUTHENTICATION_BACKENDS:
            qs |= get_groups_with_perms_roles(
                obj,
                include_domain_permissions=include_domain_permissions,
                include_model_permissions=include_model_permissions,
                for_concrete_model=for_concrete_model,
            )
        return qs.distinct()
