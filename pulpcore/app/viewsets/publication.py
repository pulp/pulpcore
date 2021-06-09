from gettext import gettext as _

from django_filters import Filter
from django_filters.rest_framework import DjangoFilterBackend, filters
from rest_framework import mixins, serializers
from rest_framework.filters import OrderingFilter

from pulpcore.app.loggers import deprecation_logger
from pulpcore.app.models import (
    ContentGuard,
    Distribution,
    Publication,
    Content,
)
from pulpcore.app.serializers import (
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


class PublicationContentFilter(Filter):
    def __init__(self, *args, **kwargs):
        kwargs.setdefault("help_text", _("Content Unit referenced by HREF"))
        super().__init__(*args, **kwargs)

    def filter(self, qs, value):
        if value is None:
            # user didn't supply a value
            return qs

        if not value:
            raise serializers.ValidationError(detail=_("No value supplied for content filter"))

        # Get the content object from the content_href
        content = NamedModelViewSet.get_resource(value, Content)

        return qs.with_content([content.pk])


class PublicationFilter(BaseFilterSet):
    repository_version = RepositoryVersionFilter()
    pulp_created = IsoDateTimeFilter()
    content = PublicationContentFilter()
    content__in = PublicationContentFilter(field_name="content", lookup_expr="in")

    class Meta:
        model = Publication
        fields = {
            "repository_version": ["exact"],
            "pulp_created": DATETIME_FILTER_OPTIONS,
        }


class ListPublicationViewSet(NamedModelViewSet, mixins.ListModelMixin):
    endpoint_name = "publications"
    queryset = Publication.objects.all()
    serializer_class = PublicationSerializer
    filterset_class = PublicationFilter

    @classmethod
    def is_master_viewset(cls):
        """Do not hide from the routers."""
        return False


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

    class Meta:
        model = Distribution
        fields = {
            "name": NAME_FILTER_OPTIONS,
            "base_path": ["exact", "contains", "icontains", "in"],
        }


class NewDistributionFilter(DistributionFilter):
    def __init__(self, *args, **kwargs):
        deprecation_logger.warning(
            "The NewDistributionFilter object is deprecated and will be removed in version 3.15. "
            "Use DistributionFilter instead."
        )
        return super().__init__(*args, **kwargs)


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
    filterset_class = DistributionFilter

    def async_reserved_resources(self, instance):
        """Return resource that locks all Distributions."""
        return ["/api/v3/distributions/"]
