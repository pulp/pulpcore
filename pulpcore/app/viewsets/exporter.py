from django_filters.rest_framework import filters
from rest_framework.decorators import action
from rest_framework import mixins

from pulpcore.app.models import (
    Export,
    ExportedResource,
    Exporter,
    PulpExporter,
    Repository,
    RepositoryVersion,
)

from pulpcore.app.serializers import (
    ExportSerializer,
    ExporterSerializer,
    PulpExporterSerializer,
)
from pulpcore.app.viewsets import (
    BaseFilterSet,
    NamedModelViewSet,
)
from pulpcore.app import tasks
from pulpcore.app.viewsets.base import NAME_FILTER_OPTIONS
from pulpcore.plugin.tasking import enqueue_with_reservation
from pulpcore.app.response import OperationPostponedResponse


class ExporterFilter(BaseFilterSet):
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
        model = Exporter
        fields = {
            'name': NAME_FILTER_OPTIONS,
        }


class ExporterViewSet(NamedModelViewSet,
                      mixins.CreateModelMixin,
                      mixins.UpdateModelMixin,
                      mixins.RetrieveModelMixin,
                      mixins.ListModelMixin,
                      mixins.DestroyModelMixin):
    queryset = Exporter.objects.all()
    serializer_class = ExporterSerializer
    endpoint_name = 'exporters'
    router_lookup = 'exporter'
    filterset_class = ExporterFilter


class ExportViewSet(NamedModelViewSet,
                    mixins.CreateModelMixin,
                    mixins.RetrieveModelMixin,
                    mixins.ListModelMixin,
                    mixins.DestroyModelMixin):
    """
    ViewSet for viewing exports from an Exporter.
    """
    endpoint_name = 'exports'
    # import pydevd_pycharm
    # pydevd_pycharm.settrace('192.168.1.109', port=3014, stdoutToServer=True, stderrToServer=True)
    nest_prefix = 'exporters'
    router_lookup = 'export'
    lookup_field = 'pk'
    parent_viewset = ExporterViewSet
    parent_lookup_kwargs = {'exporter_pk': 'exporter__pk'}
    serializer_class = ExportSerializer
    queryset = Export.objects.all()


class PulpExporterViewSet(ExporterViewSet):
    endpoint_name = 'pulp'
    serializer_class = PulpExporterSerializer
    queryset = PulpExporter.objects.all()


class ExportViewSet(NamedModelViewSet,
                    mixins.CreateModelMixin,
                    mixins.RetrieveModelMixin,
                    mixins.ListModelMixin,
                    mixins.DestroyModelMixin):
    """
    ViewSet for viewing exports from an Exporter.
    """
    endpoint_name = 'exports'
    nest_prefix = 'exporters'
    router_lookup = 'export'
    lookup_field = 'pk'
    parent_lookup_kwargs = {'exporter_pk': 'exporter__pk'}
    serializer_class = ExportSerializer
    queryset = Export.objects.all()
    parent_viewset = ExporterViewSet


class PulpExportViewSet(ExportViewSet,
                    mixins.CreateModelMixin,
                    mixins.RetrieveModelMixin,
                    mixins.ListModelMixin,
                    mixins.DestroyModelMixin):
    """
    ViewSet for viewing exports from a PulpExporter.
    """
    parent_viewset = PulpExporterViewSet

    def create(self, request, exporter_pk):
        """
        Export a set of repository-versions.

        """
        exporter = PulpExporter.objects.get(pk=exporter_pk).cast()

        result = enqueue_with_reservation(
            exporter.pulp_export,
            [exporter],
            kwargs={},
        )
        return OperationPostponedResponse(result, request)