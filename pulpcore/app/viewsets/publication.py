from django_filters.rest_framework import DjangoFilterBackend, filters
from rest_framework import mixins
from rest_framework.filters import OrderingFilter

from pulpcore.app.models import BaseDistribution, ContentGuard, Publication
from pulpcore.app.serializers import (
    BaseDistributionSerializer,
    ContentGuardSerializer,
    PublicationSerializer,
)
from pulpcore.app.viewsets import (
    AsyncCreateMixin,
    AsyncRemoveMixin,
    AsyncUpdateMixin,
    BaseFilterSet,
    NamedModelViewSet,
)
from pulpcore.app.viewsets.base import NAME_FILTER_OPTIONS, DATETIME_FILTER_OPTIONS
from pulpcore.app.viewsets.custom_filters import IsoDateTimeFilter, RepositoryVersionFilter


class PublicationFilter(BaseFilterSet):
    repository_version = RepositoryVersionFilter()
    pulp_created = IsoDateTimeFilter()

    class Meta:
        model = Publication
        fields = {
            "repository_version": ["exact"],
            "pulp_created": DATETIME_FILTER_OPTIONS,
        }


class PublicationViewSet(
    NamedModelViewSet, mixins.RetrieveModelMixin, mixins.ListModelMixin, mixins.DestroyModelMixin
):
    endpoint_name = "publications"
    queryset = Publication.objects.exclude(complete=False)
    serializer_class = PublicationSerializer
    filter_backends = (OrderingFilter, DjangoFilterBackend)
    filterset_class = PublicationFilter
    ordering = ("-pulp_created",)


class ContentGuardFilter(BaseFilterSet):
    name = filters.CharFilter()

    class Meta:
        model = ContentGuard
        fields = {
            "name": NAME_FILTER_OPTIONS,
        }


class ContentGuardViewSet(
    NamedModelViewSet,
    mixins.CreateModelMixin,
    mixins.UpdateModelMixin,
    mixins.DestroyModelMixin,
    mixins.RetrieveModelMixin,
    mixins.ListModelMixin,
):
    endpoint_name = "contentguards"
    serializer_class = ContentGuardSerializer
    queryset = ContentGuard.objects.all()
    filterset_class = ContentGuardFilter


class DistributionFilter(BaseFilterSet):
    # e.g.
    # /?name=foo
    # /?name__in=foo,bar
    # /?base_path__contains=foo
    # /?base_path__icontains=foo
    name = filters.CharFilter()
    base_path = filters.CharFilter()

    class Meta:
        model = BaseDistribution
        fields = {
            "name": NAME_FILTER_OPTIONS,
            "base_path": ["exact", "contains", "icontains", "in"],
        }


class BaseDistributionViewSet(
    NamedModelViewSet,
    mixins.RetrieveModelMixin,
    mixins.ListModelMixin,
    AsyncCreateMixin,
    AsyncRemoveMixin,
    AsyncUpdateMixin,
):
    """
    Provides read and list methods and also provides asynchronous CUD methods to dispatch tasks
    with reservation that lock all Distributions preventing race conditions during base_path
    checking.
    """

    endpoint_name = "distributions"
    queryset = BaseDistribution.objects.all()
    serializer_class = BaseDistributionSerializer
    filterset_class = DistributionFilter

    def async_reserved_resources(self, instance):
        """Return resource that locks all Distributions."""
        return ["/api/v3/distributions/"]
