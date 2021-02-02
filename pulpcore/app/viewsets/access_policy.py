from django_filters.rest_framework import filters
from rest_framework import mixins

from pulpcore.app.models import AccessPolicy
from pulpcore.app.serializers import AccessPolicySerializer
from pulpcore.app.viewsets import BaseFilterSet, NamedModelViewSet
from pulpcore.app.viewsets.base import NAME_FILTER_OPTIONS


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
