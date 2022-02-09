from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group as BaseGroup
from django.db import models
from django_currentuser.middleware import get_current_authenticated_user
from django_lifecycle import hook, LifecycleModelMixin
from guardian.models.models import GroupObjectPermission, UserObjectPermission
from guardian.shortcuts import assign_perm, remove_perm

from pulpcore.app.models import BaseModel
from pulpcore.app.util import get_viewset_for_model


def _ensure_iterable(obj):
    if isinstance(obj, str):
        return [obj]
    return obj


class AccessPolicy(BaseModel):
    """
    A model storing a viewset authorization policy and permission assignment of new objects created.

    Fields:

        creation_hooks (models.JSONField): A list of dictionaries identifying callables on the
            ``pulpcore.plugin.access_policy.AccessPolicyFromDB`` which can add user or group roles
            for newly created objects. This is a nullable field due to not all endpoints creating
            objects.
        statements (models.JSONField): A list of ``drf-access-policy`` statements.
        viewset_name (models.CharField): The name of the viewset this instance controls
            authorization for.
        customized (BooleanField): False if the AccessPolicy has been user-modified. True otherwise.
            Defaults to False.

    """

    creation_hooks = models.JSONField(null=True)
    statements = models.JSONField()
    viewset_name = models.CharField(max_length=128, unique=True)
    customized = models.BooleanField(default=False)


class AutoAddObjPermsMixin:
    """
    A mixin that automatically adds roles based on the ``creation_hooks`` data.

    To use this mixin, your model must support ``django-lifecycle``.

    This mixin adds an ``after_create`` hook which properly interprets the ``creation_hooks``
    data and calls methods also provided by this mixin to add roles.

    These mixing are provided by default:

    * ``add_for_object_creator`` will add the permissions to the creator of the object.
    * ``add_for_users`` will add the permissions for one or more users by name.
    * ``add_for_groups`` will add the permissions for one or more groups by name.
    * ``add_roles_for_object_creator`` will add the roles to the creator of the object.
    * ``add_roles_for_users`` will add the roles for one or more users by name.
    * ``add_roles_for_groups`` will add the roles for one or more groups by name.

    """

    def __init__(self, *args, **kwargs):
        self.REGISTERED_CREATION_HOOKS = {
            "add_roles_for_users": self.add_roles_for_users,
            "add_roles_for_groups": self.add_roles_for_groups,
            "add_roles_for_object_creator": self.add_roles_for_object_creator,
        }
        super().__init__(*args, **kwargs)

    @hook("after_create")
    def add_perms(self):
        viewset = get_viewset_for_model(self)
        for permission_class in viewset.get_permissions(viewset):
            if hasattr(permission_class, "handle_creation_hooks"):
                permission_class.handle_creation_hooks(self)

    def add_for_users(self, permissions, users):
        """
        Adds object-level permissions for one or more users for this newly created object.

        Args:
            permissions (str or list): One or more object-level permissions to be added for the
                users. The permission names are in the form of ``<app_name>.<codename>``, e.g.
                ``"core.change_task"``. This can either be a single permission as a string, or list
                of permission names.
            users (str or list): One or more users who will receive object-level permissions. This
                can either be a single username as a string or a list of usernames.

        Raises:
            ObjectDoesNotExist: If any of the users do not exist.

        """
        permissions = _ensure_iterable(permissions)
        users = _ensure_iterable(users)
        for username in users:
            user = get_user_model().objects.get(username=username)
            for perm in permissions:
                assign_perm(perm, user, self)

    def add_roles_for_users(self, roles, users):
        """
        Adds object-level roles for one or more users for this newly created object.

        Args:
            roles (str or list): One or more roles to be added at object-level for the users.
                This can either be a single role as a string, or a list of role names.
            users (str or list): One or more users who will receive object-level roles. This can
                either be a single username as a string or a list of usernames.

        Raises:
            ObjectDoesNotExist: If any of the users do not exist.

        """
        from pulpcore.app.role_util import assign_role

        roles = _ensure_iterable(roles)
        users = _ensure_iterable(users)
        for username in users:
            user = get_user_model().objects.get(username=username)
            for role in roles:
                assign_role(role, user, self)

    def add_for_groups(self, permissions, groups):
        """
        Adds object-level permissions for one or more groups for this newly created object.

        Args:
            permissions (str or list): One or more object-level permissions to be added for the
                groups. The permission names are in the form of ``<app_name>.<codename>``, e.g.
                ``"core.change_task"``. This can either be a single permission as a string, or list
                of permission names.
            groups (str or list): One or more groups who will receive object-level permissions. This
                can either be a single group name as a string or a list of group names.

        Raises:
            ObjectDoesNotExist: If any of the groups do not exist.

        """
        permissions = _ensure_iterable(permissions)
        groups = _ensure_iterable(groups)
        for group_name in groups:
            group = Group.objects.get(name=group_name)
            for perm in permissions:
                assign_perm(perm, group, self)

    def add_roles_for_groups(self, roles, groups):
        """
        Adds object-level roles for one or more groups for this newly created object.

        Args:
            roles (str or list): One or more object-level roles to be added for the groups. This
                can either be a single role as a string, or list of role names.
            groups (str or list): One or more groups who will receive object-level roles. This
                can either be a single group name as a string or a list of group names.

        Raises:
            ObjectDoesNotExist: If any of the groups do not exist.

        """
        from pulpcore.app.role_util import assign_role

        roles = _ensure_iterable(roles)
        groups = _ensure_iterable(groups)
        for group_name in groups:
            group = Group.objects.get(name=group_name)
            for role in roles:
                assign_role(role, group, self)

    def add_for_object_creator(self, permissions, *args):
        """
        Adds object-level permissions for the user creating the newly created object.

        If the ``django_currentuser.middleware.get_current_authenticated_user`` returns None because
        the API client did not provide authentication credentials, *no* permissions are added and
        this passes silently. This allows endpoints which create objects and do not require
        authorization to execute without error.

        Args:
            permissions (str or list): One or more object-level permissions to be added for the
                users. The permission names are in the form of ``<app_name>.<codename>``, e.g.
                ``"core.change_task"``. This can either be a single permission as a string, or list
                of permission names.

        """
        permissions = _ensure_iterable(permissions)
        current_user = get_current_authenticated_user()
        if current_user:
            for perm in permissions:
                assign_perm(perm, current_user, self)

    def add_roles_for_object_creator(self, roles):
        """
        Adds object-level roles for the user creating the newly created object.

        If the ``django_currentuser.middleware.get_current_authenticated_user`` returns None because
        the API client did not provide authentication credentials, *no* permissions are added and
        this passes silently. This allows endpoints which create objects and do not require
        authorization to execute without error.

        Args:
            roles (list or str): One or more roles to be added at the object-level for the user.
                This can either be a single role as a string, or list of role names.

        """
        from pulpcore.app.role_util import assign_role

        roles = _ensure_iterable(roles)
        current_user = get_current_authenticated_user()
        if current_user:
            for role in roles:
                assign_role(role, current_user, self)


class AutoDeleteObjPermsMixin:
    """
    A mixin that automatically deletes user and group permissions for an object prior to deletion.

    To use this mixin, your model must support ``django-lifecycle``.
    """

    @hook("before_delete")
    def delete_user_and_group_obj_perms(self):
        UserObjectPermission.objects.filter(object_pk=self.pk).delete()
        GroupObjectPermission.objects.filter(object_pk=self.pk).delete()

    def remove_for_users(self, permissions, users):
        """
        Removes object-level permissions for one or more users for this object.
        Requires AutoAddObjPermsMixin

        Args:
            permissions (str or list): One or more object-level permissions to be added for the
                users. The permission names are in the form of ``<app_name>.<codename>``, e.g.
                ``"core.change_task"``. This can either be a single permission as a string, or list
                of permission names.
            users (str or list): One or more users who will lose these object-level permissions.
                This can either be a single username as a string or a list of usernames.

        Raises:
            ObjectDoesNotExist: If any of the users do not exist.

        """
        permissions = _ensure_iterable(permissions)
        users = _ensure_iterable(users)
        for username in users:
            user = get_user_model().objects.get(username=username)
            for perm in permissions:
                remove_perm(perm, user, self)

    def remove_for_groups(self, permissions, groups):
        """
        Removes object-level permissions for one or more groups for this object.
        Requires AutoAddObjPermsMixin

        Args:
            permissions (str or list): One or more object-level permissions to be removed for the
                groups. The permission names are in the form of ``<app_name>.<codename>``, e.g.
                ``"core.change_task"``. This can either be a single permission as a string, or list
                of permission names.
            groups (str or list): One or more groups who will lose these object-level permissions.
                This can either be a single group name as a string or a list of group names.

        Raises:
            ObjectDoesNotExist: If any of the groups do not exist.

        """
        permissions = _ensure_iterable(permissions)
        groups = _ensure_iterable(groups)
        for group_name in groups:
            group = Group.objects.get(name=group_name)
            for perm in permissions:
                remove_perm(perm, group, self)


class Group(LifecycleModelMixin, BaseGroup, AutoAddObjPermsMixin):
    class Meta:
        proxy = True
        permissions = [
            ("manage_roles_group", "Can manage role assignments on group"),
        ]
