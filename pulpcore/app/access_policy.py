from rest_access_policy import AccessPolicy
from django.db.utils import ProgrammingError

from pulpcore.app.models import AccessPolicy as AccessPolicyModel
from pulpcore.app.util import get_view_urlpattern


class AccessPolicyFromDB(AccessPolicy):
    """
    An AccessPolicy that loads statements from an `AccessPolicy` model instance.
    """

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
        try:
            viewset_name = get_view_urlpattern(view)
            access_policy_obj = AccessPolicyModel.objects.get(viewset_name=viewset_name)
        except (AccessPolicyModel.DoesNotExist, AttributeError, ProgrammingError):
            default_statement = [{"action": "*", "principal": "admin", "effect": "allow"}]
            policy = getattr(view, "DEFAULT_ACCESS_POLICY", {"statements": default_statement})
            return policy["statements"]
        else:
            return access_policy_obj.statements
