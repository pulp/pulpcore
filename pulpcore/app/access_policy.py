from copy import deepcopy

from rest_access_policy import AccessPolicy
from rest_framework.exceptions import APIException

from pulpcore.app import settings
from pulpcore.app.models import AccessPolicy as AccessPolicyModel
from pulpcore.app.util import get_view_urlpattern, get_viewset_for_model


DEFAULT_ACCESS_POLICY = {"statements": [{"action": "*", "principal": "admin", "effect": "allow"}]}


class DefaultAccessPolicy(AccessPolicy):
    """
    An AccessPolicy that takes default statements from the view(set).
    """

    @classmethod
    def get_access_policy(cls, view):
        """
        Retrieves the default access policy of a view.

        Args:
            view (subclass of rest_framework.view.APIView): The view or viewset to receive the
                AccessPolicy model for.

        Returns:
            A dictionary representing the access policy.
        """
        return getattr(view, "DEFAULT_ACCESS_POLICY", DEFAULT_ACCESS_POLICY)

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
        if (creation_hooks := access_policy.get("creation_hooks")) is not None:
            for creation_hook in creation_hooks:
                hook_name = creation_hook["function"]
                try:
                    function = obj.REGISTERED_CREATION_HOOKS[hook_name]
                except KeyError:
                    raise APIException(
                        f"Creation hook '{hook_name}' was not registered for this view set."
                    )

                kwargs = creation_hook.get("parameters") or {}
                function(**kwargs)

    def scope_queryset(self, view, qs):
        """
        Scope the queryset based on the access policy `scope_queryset` method if present.
        """
        if (queryset_scoping := self.get_access_policy(view).get("queryset_scoping")) is not None:
            scope = queryset_scoping["function"]
            if not (function := getattr(view, scope, None)):
                raise APIException(
                    f"Queryset scoping method {scope} is not present on this view set."
                )
            kwargs = queryset_scoping.get("parameters") or {}
            qs = function(qs, **kwargs)
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
        # It looks like AccessPolicy is modifying the thing we give it... Tztztz
        return deepcopy(self.get_access_policy(view)["statements"])


class AccessPolicyFromSettings(DefaultAccessPolicy):
    """
    An AccessPolicy that loads statements from settings.

    If an access policy cannot be found this falls back to the default one.
    """

    @classmethod
    def get_access_policy(cls, view):
        """
        Retrieves the AccessPolicy from the DB or None if it doesn't exist.

        Args:
            view (subclass of rest_framework.view.APIView): The view or viewset to receive the
                AccessPolicy model for.

        Returns:
            A dictionary representing the access policy.
        """
        try:
            urlpattern = get_view_urlpattern(view)
            return settings.ACCESS_POLICIES[urlpattern]
        except (AttributeError, KeyError):
            # The view does not define a `urlpattern()` method, e.g. it's not a NamedModelViewset
            return super().get_access_policy(view)


class AccessPolicyFromDB(DefaultAccessPolicy):
    """
    An AccessPolicy that loads statements from an `AccessPolicy` model instance.

    If an access policy cannot be found this falls back to the default one.
    """

    @classmethod
    def get_access_policy(cls, view):
        """
        Retrieves the AccessPolicy from the DB or None if it doesn't exist.

        Args:
            view (subclass of rest_framework.view.APIView): The view or viewset to receive the
                AccessPolicy model for.

        Returns:
            A dictionary representing the access policy.
        """
        try:
            urlpattern = get_view_urlpattern(view)
        except AttributeError:
            # The view does not define a `urlpattern()` method, e.g. it's not a NamedModelViewset
            return super().get_access_policy(view)

        try:
            access_policy = AccessPolicyModel.objects.get(viewset_name=urlpattern)
            return {
                "statements": access_policy.statements,
                "queryset_scoping": access_policy.queryset_scoping,
                "creation_hooks": access_policy.creation_hooks,
            }
        except AccessPolicyModel.DoesNotExist:
            return super().get_access_policy(view)
