from gettext import gettext as _

from django.contrib.contenttypes.models import ContentType
from django.contrib.auth.backends import BaseBackend
from django.contrib.auth.models import Permission
from itertools import chain

from pulpcore.app.models.role import GroupRole
from pulpcore.app.models import Domain


class ObjectRolePermissionBackend(BaseBackend):
    def has_perm(self, user_obj, perm, obj=None):
        # Changing the signature for the backend requires changing the user model as well
        # Instead have check if obj is a Domain to see if we are checking the permission on the
        # domain-level
        if not user_obj.is_authenticated:
            return False

        try:
            app_label, codename = perm.split(".", maxsplit=1)
            permission = Permission.objects.get(
                content_type__app_label=app_label, codename=codename
            )
        except Permission.DoesNotExist:
            # Cannot have a permission that does not exist.
            return False

        if obj is None:
            # Check for global roles
            if user_obj.object_roles.filter(
                object_id=None, domain=None, role__permissions=permission
            ).exists():
                return True
            if GroupRole.objects.filter(
                group__in=user_obj.groups.all(),
                object_id=None,
                domain=None,
                role__permissions=permission,
            ).exists():
                return True
        elif isinstance(obj, Domain) and "domain" not in perm:
            # Check for domain roles
            if user_obj.object_roles.filter(
                domain_id=obj.pk, role__permissions=permission
            ).exists():
                return True
            if GroupRole.objects.filter(
                group__in=user_obj.groups.all(), domain_id=obj.pk, role__permissions=permission
            ).exists():
                return True
        else:
            obj_type = ContentType.objects.get_for_model(obj, for_concrete_model=False)
            if permission.content_type == obj_type:
                # Check object specific roles
                if user_obj.object_roles.filter(
                    object_id=obj.pk, role__permissions=permission
                ).exists():
                    return True
                if GroupRole.objects.filter(
                    group__in=user_obj.groups.all(), object_id=obj.pk, role__permissions=permission
                ).exists():
                    return True
            else:
                raise RuntimeError(
                    _("Permission {} is not suitable for objects of class {}.").format(
                        perm, obj.__class__
                    )
                )
        return False

    def get_all_permissions(self, user_obj, obj=None):
        app_label = "role__permissions__content_type__app_label"
        codename = "role__permissions__codename"

        if obj is None:
            # Returns all domain & model level permissions for user
            result = (
                user_obj.object_roles.filter(object_id=None).values(app_label, codename).distinct()
            )
            group_result = (
                GroupRole.objects.filter(group__in=user_obj.groups.all(), object_id=None)
                .values(app_label, codename)
                .distinct()
            )
            return list(
                {f"{item[app_label]}.{item[codename]}" for item in chain(result, group_result)}
            )

        else:
            obj_type = ContentType.objects.get_for_model(obj, for_concrete_model=False)
            # Maybe there is a way to reformulate this as a single query on Permissions
            result = (
                user_obj.object_roles.filter(role__permissions__content_type=obj_type)
                .filter(
                    content_type=obj_type,
                    object_id=obj.pk,
                )
                .values(codename)
                .distinct()
            )
            group_result = (
                GroupRole.objects.filter(
                    group__in=user_obj.groups.all(), role__permissions__content_type=obj_type
                )
                .filter(
                    content_type=obj_type,
                    object_id=obj.pk,
                )
                .values(codename)
                .distinct()
            )
        return list({item[codename] for item in chain(result, group_result)})
