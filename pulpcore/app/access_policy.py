import warnings

from rest_access_policy import AccessPolicy

from pulpcore.app.models import AccessPolicy as AccessPolicyModel


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

            AccessPolicyModel.objects.get(viewset_name=view.__model__.__name__)

        Args:
            request (rest_framework.request.Request): The request being checked for authorization.
            view (subclass rest_framework.viewsets.GenericViewSet): The view name being requested.

        Returns:
            The access policy statements in drf-access-policy policy structure.
        """
        try:
            access_policy_obj = AccessPolicyModel.objects.get(
                viewset_name=view.__class__.urlpattern()
            )
        except AccessPolicyModel.NotFound:
            access_policy_obj = AccessPolicyModel.objects.get(viewset_name=view.__class__.__name__)
            warnings.warn(
                "Addressing AccessPolicy via the viewset's classname is deprecated"
                "and will be removed in pulpcore==3.10; use the viewset's urlpattern().",
                warnings.DeprecationWarning,
            )
        return access_policy_obj.statements
