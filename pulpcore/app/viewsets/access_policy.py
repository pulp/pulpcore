from django_filters.rest_framework import filters
from rest_framework import mixins
from rest_framework.decorators import action
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema

from pulpcore.app.apps import pulp_plugin_configs
from pulpcore.app.models import AccessPolicy
from pulpcore.app.serializers import AccessPolicySerializer
from pulpcore.app.viewsets import BaseFilterSet, NamedModelViewSet
from pulpcore.app.viewsets.base import NAME_FILTER_OPTIONS
from pulpcore.app.util import get_view_urlpattern


class AccessPolicyFilter(BaseFilterSet):
    """
    FilterSet for AccessPolicy.
    """

    customized = filters.BooleanFilter()

    class Meta:
        model = AccessPolicy
        fields = {"viewset_name": NAME_FILTER_OPTIONS, "customized": ["exact"]}


class AccessPolicyViewSet(
    NamedModelViewSet, mixins.UpdateModelMixin, mixins.RetrieveModelMixin, mixins.ListModelMixin
):
    """
    ViewSet for AccessPolicy.

    NOTE: This API endpoint is in "tech preview" and subject to change

    """

    queryset = AccessPolicy.objects.all()
    serializer_class = AccessPolicySerializer
    endpoint_name = "access_policies"
    ordering = "viewset_name"
    filterset_class = AccessPolicyFilter

    @extend_schema(request=None)
    @action(detail=True, methods=["post"])
    def reset(self, request, pk=None):
        """
        Reset the access policy to its uncustomized default value.
        """

        access_policy = self.get_object()
        for plugin_config in pulp_plugin_configs():
            for viewset_batch in plugin_config.named_viewsets.values():
                for viewset in viewset_batch:
                    if get_view_urlpattern(viewset) == access_policy.viewset_name:
                        default_access_policy = viewset.DEFAULT_ACCESS_POLICY
                        access_policy.statements = default_access_policy["statements"]
                        access_policy.creation_hooks = default_access_policy.get(
                            "creation_hooks"
                        ) or default_access_policy.get("permissions_assignment")
                        access_policy.customized = False
                        access_policy.save()
                        serializer = AccessPolicySerializer(
                            access_policy, context={"request": request}
                        )
                        return Response(serializer.data)
        raise RuntimeError("Viewset for access policy was not found.")
