from django_filters.rest_framework import filters
from drf_yasg.utils import swagger_auto_schema
from rest_framework import mixins

from pulpcore.app.models import (
    Export,
    Exporter,
    PulpExport,
    PulpExporter,
)

from pulpcore.app.serializers import (
    AsyncOperationResponseSerializer,
    ExportSerializer,
    ExporterSerializer,
    PulpExporterSerializer,
    PulpExportSerializer,
)

from pulpcore.app.tasks.export import pulp_export

from pulpcore.app.viewsets import (
    BaseFilterSet,
    NamedModelViewSet,
)
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
    """
    ViewSet for viewing exporters.
    """
    queryset = Exporter.objects.all()
    serializer_class = ExporterSerializer
    endpoint_name = 'exporters'
    router_lookup = 'exporter'
    filterset_class = ExporterFilter


class PulpExporterViewSet(ExporterViewSet):
    """
    ViewSet for viewing PulpExporters.
    """
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


class PulpExportViewSet(ExportViewSet):
    """
    ViewSet for viewing exports from a PulpExporter.
    """
    parent_viewset = PulpExporterViewSet
    serializer_class = PulpExportSerializer
    queryset = PulpExport.objects.all()

    @swagger_auto_schema(
        request_body=PulpExportSerializer,
        operation_description="Trigger an asynchronous task to export a set of repositories",
        responses={202: AsyncOperationResponseSerializer}
    )
    def create(self, request, exporter_pk):
        """
        Generates a Task to export the set of repositories assigned to a specific PulpExporter.
        """
        exporter = PulpExporter.objects.get(pk=exporter_pk).cast()

        result = enqueue_with_reservation(
            pulp_export,
            [exporter],
            kwargs={'pulp_exporter': exporter},
        )
        return OperationPostponedResponse(result, request)
