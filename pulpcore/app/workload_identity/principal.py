"""A stateless ``request.user`` for workload-identity clients.

It does not subclass the user model, and answers permission checks from its own grants so Django
never dispatches them to ``AUTHENTICATION_BACKENDS``.
"""

from pulpcore.app.workload_identity.authz import has_grant_perm, permissions_for


class WorkloadIdentityPrincipal:
    """A user-like object backed by grants rather than a database row, safe as ``request.user``."""

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

    @property
    def groups(self):
        """The ``Group`` objects named by ``group_names`` (empty by default)."""
        from pulpcore.app.models import Group

        return Group.objects.filter(name__in=self.group_names)

    def has_perm(self, perm, obj=None):
        """Whether the grants confer ``perm`` (optionally scoped to ``obj``)."""
        return has_grant_perm(self.grants, perm, obj)

    def has_perms(self, perm_list, obj=None):
        """Whether the grants confer every permission in ``perm_list``."""
        return all(self.has_perm(perm, obj) for perm in perm_list)

    def has_module_perms(self, app_label):
        """Whether the grants confer any permission in ``app_label``."""
        prefix = f"{app_label}."
        return any(perm.startswith(prefix) for perm in self.get_all_permissions())

    def get_all_permissions(self, obj=None):
        """``app_label.codename`` at the model level, bare codenames for an object (Pulp's convention)."""
        perms = permissions_for(self.grants, obj)
        if obj is None:
            return perms
        return {perm.split(".", 1)[1] for perm in perms}

    def get_group_permissions(self, obj=None):
        """The permissions from groups; always empty for a principal."""
        return set()

    def __str__(self):
        """The username, or ``"workload-identity"`` when it is empty."""
        return self.username or "workload-identity"
