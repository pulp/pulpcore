from gettext import gettext as _

from django_filters.rest_framework import filters
from rest_framework import mixins
from rest_framework.decorators import action

from pulpcore.app.models import AlternateContentSource
from pulpcore.app.serializers import AlternateContentSourceSerializer
from pulpcore.app.viewsets import BaseFilterSet, NamedModelViewSet
from pulpcore.app.viewsets.base import NAME_FILTER_OPTIONS


class AlternateContentSourceFilter(BaseFilterSet):
    """FilterSet for ACS."""

    name = filters.CharFilter()

    class Meta:
        model = AlternateContentSource
        fields = {
            "name": NAME_FILTER_OPTIONS,
        }


class AlternateContentSourceViewSet(
    mixins.CreateModelMixin,
    mixins.DestroyModelMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    NamedModelViewSet,
):
    """
    A class for ACS viewset.
    """

    queryset = AlternateContentSource.objects.all()
    serializer_class = AlternateContentSourceSerializer
    endpoint_name = "acs"
    router_lookup = "acs"
    filterset_class = AlternateContentSourceFilter

    @action(detail=True, methods=["post"])
    def refresh(self, request, pk=None):
        raise NotImplementedError(_("Method not implemented by plugin writer!"))
