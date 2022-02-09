from rest_access_policy import AccessPolicy

from pulpcore.app.loggers import deprecation_logger
from pulpcore.app.models import AccessPolicy as AccessPolicyModel
from pulpcore.app.util import get_view_urlpattern, get_viewset_for_model
from pulpcore.app.role_util import get_objects_for_user


class AccessPolicyFromDB(AccessPolicy):
    """
    An AccessPolicy that loads statements from an `AccessPolicy` model instance.
    """

    @staticmethod
    def get_access_policy(view):
        """
        Retrieves the AccessPolicy from the DB or None if it doesn't exist.

        Args:
            view (subclass of rest_framework.view.APIView): The view or viewset to receive the
                AccessPolicy model for.

        Returns:
            Either a `pulpcore.app.models.AccessPolicy` or None.
        """
        try:
            urlpattern = get_view_urlpattern(view)
        except AttributeError:
            # The view does not define a `urlpattern()` method, e.g. it's not a NamedModelViewset
            return None

        try:
            return AccessPolicyModel.objects.get(viewset_name=urlpattern)
        except AccessPolicyModel.DoesNotExist:
            return None

    @classmethod
    def handle_creation_hooks(cls, obj):
        """
        Handle the creation hooks defined in this policy for the passed in `obj`.

        Args:
            cls: The class this method belongs to.
            obj: The model instance to have its creation hooks handled for.

        """
        viewset = get_viewset_for_model(obj)
        access_policy = cls.get_access_policy(viewset)
        if access_policy and access_policy.creation_hooks is not None:
            for creation_hook in access_policy.creation_hooks:
                function = obj.REGISTERED_CREATION_HOOKS.get(creation_hook["function"])
                if function is not None:
                    kwargs = creation_hook.get("parameters") or {}
                    function(**kwargs)
                else:
                    # Old interface deprecated for removal in 3.20
                    function = getattr(obj, creation_hook["function"])
                    deprecation_logger.warn(
                        "Calling unregistered creation hooks from the access policy is deprecated"
                        " and may be removed with pulpcore 3.20."
                        f"[hook={creation_hook}, viewset={access_policy.viewset_name}]."
                    )
                    function(creation_hook.get("permissions"), creation_hook.get("parameters"))

    def scope_queryset(self, view, qs):
        """
        Scope the queryset based on the view's `default_queryset_filtering_permissions`.
        """
        permission_name = getattr(view, "queryset_filtering_required_permission", None)
        if permission_name:
            user = view.request.user
            qs = get_objects_for_user(user, permission_name, qs)
        return qs

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
