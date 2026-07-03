"""A stateless principal used as ``request.user`` for OIDC-authenticated clients.

``OIDCPrincipal`` deliberately does not subclass Django's user model or
``PermissionsMixin``. It implements its own permission-checking methods so that
Django never dispatches permission checks for it to ``AUTHENTICATION_BACKENDS``.
Authorization is derived entirely from the list of grants carried on the object.
"""

from pulpcore.app.oidc.authz import has_grant_perm, permissions_for


class OIDCPrincipal:
    """A user-like object backed by OIDC grants rather than a database row.

    This object is safe to assign to ``request.user``. It exposes the attributes
    the request path reads and answers permission checks from its ``grants``.

    Attributes:
        grants (list): The list of grant dicts backing this principal.
        username (str): The principal's username (may be empty).
    """

    is_authenticated = True
    is_active = True
    is_anonymous = False
    is_superuser = False
    is_staff = False
    pk = None
    id = None

    def __init__(self, grants, username=""):
        """Initialize the principal.

        Args:
            grants (list): A list of grant dicts (see ``authz`` for the shape).
            username (str): The principal's username. Defaults to an empty string.
        """
        self.grants = grants
        self.username = username

    @property
    def groups(self):
        """An empty ``Group`` queryset so ``user.groups.all()`` never crashes."""
        from pulpcore.app.models import Group

        return Group.objects.none()

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
        """The set of ``app_label.codename`` permissions the grants confer."""
        return permissions_for(self.grants)

    def get_group_permissions(self, obj=None):
        """The permissions from groups; always empty for a principal."""
        return set()

    def __str__(self):
        """The username, or ``"oidc-principal"`` when it is empty."""
        return self.username or "oidc-principal"
