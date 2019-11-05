from django_filters.rest_framework import filters
from rest_framework import mixins

from pulpcore.app.models import (
    FileSystemExporter
)
from pulpcore.app.serializers import (
    FileSystemExporterSerializer
)
from pulpcore.app.viewsets import (
    BaseFilterSet,
    NamedModelViewSet,
)
from pulpcore.app.viewsets.base import NAME_FILTER_OPTIONS


class FileSystemExporterFilter(BaseFilterSet):
    """
    Plugin file system exporter filter should:
     - inherit from this class
     - add any specific filters if needed
     - define a `Meta` class which should:
       - specify a plugin remote model for which filter is defined
       - extend `fields` with specific ones
    """
    name = filters.CharFilter()

    class Meta:
        model = FileSystemExporter
        fields = {
            'name': NAME_FILTER_OPTIONS,
        }


class FileSystemExporterViewSet(NamedModelViewSet,
                                mixins.CreateModelMixin,
                                mixins.UpdateModelMixin,
                                mixins.RetrieveModelMixin,
                                mixins.ListModelMixin,
                                mixins.DestroyModelMixin):
    endpoint_name = 'file_exporters'
    serializer_class = FileSystemExporterSerializer
    queryset = FileSystemExporter.objects.all()
    filterset_class = FileSystemExporterFilter
