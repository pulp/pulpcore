from gettext import gettext as _

from django_filters.rest_framework import DjangoFilterBackend, filters
from rest_framework import mixins
from rest_framework.filters import OrderingFilter

from pulpcore.app.models import BaseDistribution, ContentGuard, Distribution, Publication
from pulpcore.app.serializers import (
    BaseDistributionSerializer,
    ContentGuardSerializer,
    DistributionSerializer,
    PublicationSerializer,
)
from pulpcore.app.viewsets import (
    AsyncCreateMixin,
    AsyncRemoveMixin,
    AsyncUpdateMixin,
    BaseFilterSet,
    NamedModelViewSet,
)
from pulpcore.app.viewsets.base import DATETIME_FILTER_OPTIONS, NAME_FILTER_OPTIONS
from pulpcore.app.viewsets.custom_filters import (
    IsoDateTimeFilter,
    LabelSelectFilter,
    RepositoryVersionFilter,
)
from pulpcore.app.loggers import deprecation_logger


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


class BaseContentGuardViewSet(NamedModelViewSet):
    endpoint_name = "contentguards"
    serializer_class = ContentGuardSerializer
    queryset = ContentGuard.objects.all()
    filterset_class = ContentGuardFilter


class ListContentGuardViewSet(
    BaseContentGuardViewSet,
    mixins.ListModelMixin,
):
    """Endpoint to list all contentguards."""

    @classmethod
    def is_master_viewset(cls):
        """Do not hide from the routers."""
        return False


class ContentGuardViewSet(
    BaseContentGuardViewSet,
    mixins.CreateModelMixin,
    mixins.UpdateModelMixin,
    mixins.DestroyModelMixin,
    mixins.RetrieveModelMixin,
    mixins.ListModelMixin,
):
    """
    A viewset for contentguards.
    """


class DistributionFilter(BaseFilterSet):
    # e.g.
    # /?name=foo
    # /?name__in=foo,bar
    # /?base_path__contains=foo
    # /?base_path__icontains=foo
    name = filters.CharFilter()
    base_path = filters.CharFilter()
    pulp_label_select = LabelSelectFilter()

    def __init__(self, *args, **kwargs):
        """Initialize a DistributionFilter and emit deprecation warnings"""
        deprecation_logger.warn(
            _(
                "DistributionFilter is deprecated and could be removed as early as "
                "pulpcore==3.13; use pulpcore.plugin.serializers.NewDistributionFilter instead."
            )
        )
        return super().__init__(*args, **kwargs)

    class Meta:
        model = BaseDistribution
        fields = {
            "name": NAME_FILTER_OPTIONS,
            "base_path": ["exact", "contains", "icontains", "in"],
        }


class NewDistributionFilter(BaseFilterSet):
    # e.g.
    # /?name=foo
    # /?name__in=foo,bar
    # /?base_path__contains=foo
    # /?base_path__icontains=foo
    name = filters.CharFilter()
    base_path = filters.CharFilter()
    pulp_label_select = LabelSelectFilter()

    class Meta:
        model = Distribution
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

    def __init__(self, *args, **kwargs):
        """Initialize a BaseDistributionViewSet and emit deprecation warnings"""
        deprecation_logger.warn(
            _(
                "BaseDistributionViewSet is deprecated and could be removed as early as "
                "pulpcore==3.13; use pulpcore.plugin.viewsets.DistributionViewset instead."
            )
        )
        return super().__init__(*args, **kwargs)

    def async_reserved_resources(self, instance):
        """Return resource that locks all Distributions."""
        return ["/api/v3/distributions/"]


class DistributionViewSet(
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
    queryset = Distribution.objects.all()
    serializer_class = DistributionSerializer
    filterset_class = NewDistributionFilter

    def async_reserved_resources(self, instance):
        """Return resource that locks all Distributions."""
        return ["/api/v3/distributions/"]
