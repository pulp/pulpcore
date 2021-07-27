from abc import ABC, abstractmethod
from contextlib import suppress

from django.contrib.auth.models import Permission
from guardian.shortcuts import assign_perm, remove_perm


class Role(ABC):
    """
    An object that all Role implementations must inherit from.
    """

    @property
    @abstractmethod
    def permissions(self):
        pass


class TaskOwner(Role):

    permissions = ["core.view_task", "core.delete_task", "core.change_task"]


def _ensure_subclass_of_role(role):
    if role is Role or not issubclass(role, Role):
        raise TypeError(f"{role} must be a subclass of pulpcore.app.roles.Role")


def assign_role(role, user_or_group, obj=None):
    _ensure_subclass_of_role(role)
    for permission_name in  role.permissions:
        with suppress(Permission.DoesNotExist):
            assign_perm(permission_name, user_or_group, obj)


def remove_role(role, user_or_group, obj=None):
    _ensure_subclass_of_role(role)
    for permission_name in role.permissions:
        remove_perm(permission_name, user_or_group, obj)
