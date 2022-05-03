from django.http import Http404
from django_filters.rest_framework import filters
from drf_spectacular.utils import extend_schema
from rest_framework import mixins

from pulpcore.app.models import (
    Import,
    Importer,
    PulpImport,
    PulpImporter,
    TaskGroup,
)
from pulpcore.app.response import TaskGroupOperationResponse
from pulpcore.app.serializers import (
    ImportSerializer,
    ImporterSerializer,
    PulpImporterSerializer,
    PulpImportSerializer,
    TaskGroupOperationResponseSerializer,
)
from pulpcore.app.tasks import pulp_import
from pulpcore.app.viewsets import (
    BaseFilterSet,
    NamedModelViewSet,
)
from pulpcore.app.viewsets.base import NAME_FILTER_OPTIONS
from pulpcore.tasking.tasks import dispatch


class ImporterFilter(BaseFilterSet):
    """Filter for Importers."""

    name = filters.CharFilter()

    class Meta:
        model = Importer
        fields = {
            "name": NAME_FILTER_OPTIONS,
        }


class ImporterViewSet(
    NamedModelViewSet,
    mixins.CreateModelMixin,
    mixins.UpdateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.ListModelMixin,
    mixins.DestroyModelMixin,
):
    """ViewSet for Importers."""

    queryset = Importer.objects.all()
    serializer_class = ImporterSerializer
    endpoint_name = "importers"
    router_lookup = "importer"
    filterset_class = ImporterFilter


class ImportViewSet(
    NamedModelViewSet,
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.ListModelMixin,
    mixins.DestroyModelMixin,
):
    """ViewSet for viewing imports from an Importer."""

    endpoint_name = "imports"
    nest_prefix = "importers"
    router_lookup = "import"
    lookup_field = "pk"
    parent_viewset = ImporterViewSet
    parent_lookup_kwargs = {"importer_pk": "importer__pk"}
    serializer_class = ImportSerializer
    queryset = Import.objects.all()


class PulpImporterViewSet(ImporterViewSet):
    """ViewSet for PulpImporters."""

    endpoint_name = "pulp"
    serializer_class = PulpImporterSerializer
    queryset = PulpImporter.objects.all()


class PulpImportViewSet(ImportViewSet):
    """ViewSet for PulpImports."""

    parent_viewset = PulpImporterViewSet
    queryset = PulpImport.objects.all()

    @extend_schema(
        request=PulpImportSerializer,
        description="Trigger an asynchronous task to import a Pulp export.",
        responses={202: TaskGroupOperationResponseSerializer},
    )
    def create(self, request, importer_pk):
        """Import a Pulp export into Pulp."""
        try:
            importer = PulpImporter.objects.get(pk=importer_pk)
        except PulpImporter.DoesNotExist:
            raise Http404

        serializer = PulpImportSerializer(
            data=request.data, context={"request": request, "importer": importer}
        )
        serializer.is_valid(raise_exception=True)

        path = serializer.validated_data.get("path")
        toc = serializer.validated_data.get("toc")
        create_repositories = serializer.validated_data.get("create_repositories")
        task_group = TaskGroup.objects.create(description=f"Import of {path}")

        dispatch(
            pulp_import,
            exclusive_resources=[importer],
            task_group=task_group,
            kwargs={
                "importer_pk": importer.pk,
                "path": path,
                "toc": toc,
                "create_repositories": create_repositories,
            },
        )
        return TaskGroupOperationResponse(task_group, request)
