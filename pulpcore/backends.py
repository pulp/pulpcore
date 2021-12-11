from gettext import gettext as _

from django.contrib.contenttypes.models import ContentType
from django.contrib.auth.backends import BaseBackend
from django.contrib.auth.models import Permission

from pulpcore.app.models.role import GroupRole


class ObjectRolePermissionBackend(BaseBackend):
    def has_perm(self, user_obj, perm, obj=None):
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
            if user_obj.object_roles.filter(object_id=None, role__permissions=permission).exists():
                return True
            if GroupRole.objects.filter(
                group__in=user_obj.groups.all(), object_id=None, role__permissions=permission
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
        if obj is None:
            result = (
                user_obj.object_roles.filter(object_id=None)
                .values("role__permissions__content_type__app_label", "role__permissions__codename")
                .distinct()
            )
            group_result = (
                GroupRole.objects.filter(group__in=user_obj.groups.all(), object_id=None)
                .values("role__permissions__content_type__app_label", "role__permissions__codename")
                .distinct()
            )
            return [
                item["role__permissions__content_type__app_label"]
                + "."
                + item["role__permissions__codename"]
                for item in result
            ] + [
                item["role__permissions__content_type__app_label"]
                + "."
                + item["role__permissions__codename"]
                for item in group_result
            ]

        else:
            obj_type = ContentType.objects.get_for_model(obj, for_concrete_model=False)
            # Maybe there is a way to reformulate this as a single query on Permissions
            result = (
                user_obj.object_roles.filter(role__permissions__content_type=obj_type)
                .filter(
                    content_type=obj_type,
                    object_id=obj.pk,
                )
                .values("role__permissions__codename")
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
                .values("role__permissions__codename")
                .distinct()
            )
        return [item["role__permissions__codename"] for item in result] + [
            item["role__permissions__codename"] for item in group_result
        ]
