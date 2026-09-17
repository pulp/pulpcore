"""A stateless `request.user` for workload-identity clients.

It is not a database row. It carries the grants earned by the token and delegates permission
checks to `AUTHENTICATION_BACKENDS` like any user, where `WorkloadIdentityBackend` answers
them. It exposes the empty relations the other backends read so they run without a database id.
"""

from django.contrib.auth.models import (
    _user_get_permissions,
    _user_has_module_perms,
    _user_has_perm,
)

from pulpcore.app.models import Group
from pulpcore.app.models.role import UserRole


class WorkloadIdentityPrincipal:
    """A user-like object backed by grants rather than a database row, safe as `request.user`."""

    is_authenticated = True
    is_active = True
    is_anonymous = False
    is_superuser = False
    is_staff = False
    pk = None
    id = None
    group_names = ()

    def __init__(self, grants, username=""):
        self.grants = grants
        self.username = username
        # Prime ModelBackend's permission caches so it reports nothing for this id-less principal
        # instead of querying the database (which would fail without a user id).
        self._perm_cache = set()
        self._user_perm_cache = set()
        self._group_perm_cache = set()

    @property
    def groups(self):
        """The `Group` objects named by `group_names` (empty by default)."""
        return Group.objects.filter(name__in=self.group_names)

    @property
    def object_roles(self):
        """No stored role assignments; an empty queryset the role backend can read."""
        return UserRole.objects.none()

    def has_perm(self, perm, obj=None):
        return _user_has_perm(self, perm, obj)

    def has_perms(self, perm_list, obj=None):
        return all(self.has_perm(perm, obj) for perm in perm_list)

    def has_module_perms(self, app_label):
        return _user_has_module_perms(self, app_label)

    def get_all_permissions(self, obj=None):
        return _user_get_permissions(self, obj, "all")

    def get_group_permissions(self, obj=None):
        return _user_get_permissions(self, obj, "group")

    def __str__(self):
        """The username, or `"workload-identity"` when it is empty."""
        return self.username or "workload-identity"
