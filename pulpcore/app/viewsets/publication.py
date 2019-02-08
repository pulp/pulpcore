from django_filters.rest_framework import filters, DjangoFilterBackend
from rest_framework import mixins
from rest_framework.filters import OrderingFilter

from pulpcore.app.models import (
    ContentGuard,
    Distribution,
    Publication,
)
from pulpcore.app.serializers import (
    ContentGuardSerializer,
    DistributionSerializer,
    PublicationSerializer,
)
from pulpcore.app.viewsets import (
    BaseFilterSet,
    NamedModelViewSet
)
from pulpcore.app.viewsets.base import NAME_FILTER_OPTIONS


class PublicationViewSet(NamedModelViewSet,
                         mixins.RetrieveModelMixin,
                         mixins.ListModelMixin,
                         mixins.DestroyModelMixin):
    endpoint_name = 'publications'
    queryset = Publication.objects.exclude(complete=False)
    serializer_class = PublicationSerializer
    filter_backends = (OrderingFilter, DjangoFilterBackend)
    ordering = ('-_created',)


class ContentGuardFilter(BaseFilterSet):
    name = filters.CharFilter()

    class Meta:
        model = ContentGuard
        fields = {
            'name': NAME_FILTER_OPTIONS,
        }


class ContentGuardViewSet(NamedModelViewSet,
                          mixins.CreateModelMixin,
                          mixins.UpdateModelMixin,
                          mixins.DestroyModelMixin,
                          mixins.RetrieveModelMixin,
                          mixins.ListModelMixin):
    endpoint_name = 'contentguards'
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
        model = Distribution
        fields = {
            'name': NAME_FILTER_OPTIONS,
            'base_path': ['exact', 'contains', 'icontains', 'in']
        }


class DistributionViewSet(NamedModelViewSet,
                          mixins.AsyncCreateMixin,
                          mixins.AsyncUpdateMixin,
                          mixins.RetrieveModelMixin,
                          mixins.ListModelMixin,
                          mixins.AsyncDeleteMixin):
    endpoint_name = 'distributions'
    queryset = Distribution.objects.all()
    serializer_class = DistributionSerializer
    filterset_class = DistributionFilter
