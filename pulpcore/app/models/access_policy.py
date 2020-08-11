from gettext import gettext as _

from django.core.exceptions import ImproperlyConfigured
from django.contrib.auth.models import Group, User
from django.contrib.postgres.fields import JSONField
from django.db import models
from django_currentuser.middleware import get_current_authenticated_user
from django_lifecycle import hook
from guardian.models.models import GroupObjectPermission, UserObjectPermission
from guardian.shortcuts import assign_perm

from pulpcore.app.models import BaseModel


class AccessPolicy(BaseModel):
    """
    A model storing a viewset authorization policy and permission assignment of new objects created.

    Fields:

        permissions_assignment (JSONField): A list of dictionaries identifying callables on the
            `pulpcore.plugin.access_policy.AccessPolicyFromDB` which add user or group permissions
            for newly created objects.
        statements (JSONField): A list of `drf-access-policy` statements.
        viewset_name (models.CharField): The name of the viewset this instance controls
            authorization for.

    """

    permissions_assignment = JSONField()
    statements = JSONField()
    viewset_name = models.CharField(max_length=128, unique=True)


class AutoAddObjPermsMixin:
    """
    A mixin that automatically adds permissions based on the `permissions_assignment` data.

    To use this mixin, your model must support `django-lifecycle`.

    To use this mixin, you must define a class attribute named `ACCESS_POLICY_VIEWSET_NAME`
    containing the name of the ViewSet associated with this object.

    This mixin adds an `after_create` hook which properly interprets the `permissions_assignment`
    data and calls methods also provided by this mixin to add permissions.

    Three mixing are provided by default:

    * `add_for_object_creator` will add the permissions to the creator of the object.
    * `add_for_users` will add the permissions for one or more users by name.
    * `add_for_groups` will add the permissions for one or more groups by name.

    """

    @hook("after_create")
    def add_perms(self):
        try:
            access_policy = AccessPolicy.objects.get(viewset_name=self.ACCESS_POLICY_VIEWSET_NAME)
        except AttributeError:
            raise ImproperlyConfigured(
                _(
                    "When using the `AutoAddObjPermsMixin`, plugin writers must declare an"
                    "`ACCESS_POLICY_VIEWSET_NAME` class attribute."
                )
            )
        self._handle_permissions_assignments(access_policy)

    def _handle_permissions_assignments(self, access_policy):
        for permission_assignment in access_policy.permissions_assignment:
            callable = getattr(self, permission_assignment["function"])
            callable(permission_assignment["permissions"], permission_assignment["parameters"])

    @staticmethod
    def _ensure_iterable(obj):
        if isinstance(obj, str):
            return [obj]
        return obj

    def add_for_users(self, permissions, users):
        permissions = self._ensure_iterable(permissions)
        users = self._ensure_iterable(users)
        for username in users:
            user = User.objects.get(username=username)
            for perm in permissions:
                assign_perm(perm, user, self)

    def add_for_groups(self, permissions, groups):
        permissions = self._ensure_iterable(permissions)
        groups = self._ensure_iterable(groups)
        for group_name in groups:
            group = Group.objects.get(name=group_name)
            for perm in permissions:
                assign_perm(perm, group, self)

    def add_for_object_creator(self, permissions, *args):
        permissions = self._ensure_iterable(permissions)
        for perm in permissions:
            assign_perm(perm, get_current_authenticated_user(), self)


class AutoDeleteObjPermsMixin:
    """
    A mixin that automatically deletes user and group permissions for an object prior to deletion.

    To use this mixin, your model must support `django-lifecycle`.
    """

    @hook("before_delete")
    def delete_user_and_group_obj_perms(self):
        UserObjectPermission.objects.filter(object_pk=self.pk).delete()
        GroupObjectPermission.objects.filter(object_pk=self.pk).delete()
