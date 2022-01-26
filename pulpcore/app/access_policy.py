from rest_access_policy import AccessPolicy
from django.db.utils import ProgrammingError

from pulpcore.app.models import AccessPolicy as AccessPolicyModel
from pulpcore.app.util import get_view_urlpattern
from pulpcore.app.role_util import get_objects_for_user


class AccessPolicyFromDB(AccessPolicy):
    """
    An AccessPolicy that loads statements from an `AccessPolicy` model instance.
    """

    def get_access_policy(self, view):
        """Retrieves the AccessPolicy from the DB or None if it doesn't exist."""
        try:
            viewset_name = get_view_urlpattern(view)
            return AccessPolicyModel.objects.get(viewset_name=viewset_name)
        except (AccessPolicyModel.DoesNotExist, AttributeError, ProgrammingError):
            return None

    def get_policy_statements(self, request, view):
        """
        Return the policy statements from an AccessPolicy instance matching the viewset name.

        This is an implementation of a method that will be called by
        `rest_access_policy.AccessPolicy`. See the drf-access-policy docs for more info:

        https://rsinger86.github.io/drf-access-policy/loading_external_source/

        The `pulpcore.plugin.models.AccessPolicy` instance is looked up by the `viewset_name`
        attribute using::

            AccessPolicyModel.objects.get(viewset_name=get_view_urlpattern(view))

        If a matching `pulpcore.plugin.models.AccessPolicy` cannot be found, a default behavior of
        allowing only admin users to perform any operation is used. This fallback allows the Pulp
        RBAC implementation to be turned on endpoint-by-endpoint with less effort.

        Args:
            request (rest_framework.request.Request): The request being checked for authorization.
            view (subclass rest_framework.viewsets.GenericViewSet): The view name being requested.

        Returns:
            The access policy statements in drf-access-policy policy structure.
        """
        if access_policy_obj := self.get_access_policy(view):
            return access_policy_obj.statements
        else:
            default_statement = [{"action": "*", "principal": "admin", "effect": "allow"}]
            policy = getattr(view, "DEFAULT_ACCESS_POLICY", {"statements": default_statement})
            return policy["statements"]

    def get_default_filtering_permissions(self, view):
        """
        Gets the default filtering permissions used for queryset scoping.
        """
        if access_policy_obj := self.get_access_policy(view):
            return access_policy_obj.get("filtering_permissions", [])
        else:
            policy = getattr(view, "DEFAULT_ACCESS_POLICY", {})
            return policy.get("filtering_permissions", [])

    def objects_for_user(self, view, user, qs):
        """
        Filters the queryset to only include objects the user has permission to see based on
        the `filtering_permissions` of the access policy.
        """
        permissions = self.get_default_filtering_permissions(view)
        if not permissions:
            return qs

        return get_objects_for_user(user, permissions, qs)
