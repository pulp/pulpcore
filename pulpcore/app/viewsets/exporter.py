from drf_spectacular.utils import extend_schema
from rest_framework import mixins

from pulpcore.app.models import (
    Export,
    Exporter,
    FilesystemExport,
    FilesystemExporter,
    Publication,
    PulpExport,
    PulpExporter,
    RepositoryVersion,
)

from pulpcore.app.serializers import (
    AsyncOperationResponseSerializer,
    ExportSerializer,
    ExporterSerializer,
    FilesystemExporterSerializer,
    FilesystemExportSerializer,
    PulpExporterSerializer,
    PulpExportSerializer,
)

from pulpcore.app.tasks.export import fs_publication_export, fs_repo_version_export, pulp_export

from pulpcore.app.viewsets import (
    AsyncRemoveMixin,
    AsyncUpdateMixin,
    NamedModelViewSet,
)
from pulpcore.app.viewsets.base import NAME_FILTER_OPTIONS
from pulpcore.plugin.tasking import dispatch
from pulpcore.app.response import OperationPostponedResponse


class ExporterViewSet(
    NamedModelViewSet,
    mixins.CreateModelMixin,
    AsyncUpdateMixin,
    mixins.RetrieveModelMixin,
    mixins.ListModelMixin,
    AsyncRemoveMixin,
):
    """
    ViewSet for viewing exporters.
    """

    queryset = Exporter.objects.all()
    serializer_class = ExporterSerializer
    endpoint_name = "exporters"
    router_lookup = "exporter"
    filterset_fields = {
        "name": NAME_FILTER_OPTIONS,
    }


class PulpExporterViewSet(ExporterViewSet):
    """
    ViewSet for viewing PulpExporters.
    """

    endpoint_name = "pulp"
    serializer_class = PulpExporterSerializer
    queryset = PulpExporter.objects.all()


class FilesystemExporterViewSet(ExporterViewSet):
    """
    Endpoint for managing FilesystemExporters. FilesystemExporters are provided as a tech preview.
    """

    endpoint_name = "filesystem"
    serializer_class = FilesystemExporterSerializer
    queryset = FilesystemExporter.objects.all()


class ExportViewSet(
    NamedModelViewSet,
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.ListModelMixin,
    mixins.DestroyModelMixin,
):
    """
    ViewSet for viewing exports from an Exporter.
    """

    endpoint_name = "exports"
    nest_prefix = "exporters"
    router_lookup = "export"
    lookup_field = "pk"
    parent_lookup_kwargs = {"exporter_pk": "exporter__pk"}
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

    @extend_schema(
        request=PulpExportSerializer,
        description="Trigger an asynchronous task to export a set of repositories",
        responses={202: AsyncOperationResponseSerializer},
    )
    def create(self, request, exporter_pk):
        """
        Generates a Task to export the set of repositories assigned to a specific PulpExporter.
        """
        # Validate Exporter
        exporter = PulpExporter.objects.get(pk=exporter_pk).cast()
        ExporterSerializer.validate_path(exporter.path, check_is_dir=True)

        # Validate Export
        serializer = PulpExportSerializer(data=request.data, context={"exporter": exporter})
        serializer.is_valid(raise_exception=True)

        # Invoke the export
        task = dispatch(
            pulp_export,
            exclusive_resources=[exporter],
            shared_resources=exporter.repositories.all(),
            kwargs={"exporter_pk": str(exporter.pk), "params": request.data},
        )

        return OperationPostponedResponse(task, request)


class FilesystemExportViewSet(ExportViewSet):
    """
    Endpoint for managing FilesystemExports. This endpoint is provided as a tech preview.
    """

    parent_viewset = FilesystemExporterViewSet
    serializer_class = FilesystemExportSerializer
    queryset = FilesystemExport.objects.all()

    @extend_schema(
        request=FilesystemExportSerializer,
        description="Trigger an asynchronous task to export files to the filesystem",
        responses={202: AsyncOperationResponseSerializer},
    )
    def create(self, request, exporter_pk):
        """
        Generates a Task to export files to the filesystem.
        """
        # Validate Exporter
        exporter = FilesystemExporter.objects.get(pk=exporter_pk).cast()
        ExporterSerializer.validate_path(exporter.path, check_is_dir=True)

        # Validate Export
        serializer = FilesystemExportSerializer(data=request.data, context={"exporter": exporter})
        serializer.is_valid(raise_exception=True)

        start_repository_version_pk = None
        if request.data.get("start_repository_version"):
            start_repository_version_pk = self.get_resource(
                request.data["start_repository_version"], RepositoryVersion
            ).pk

        if request.data.get("publication"):
            publication = self.get_resource(request.data["publication"], Publication)
            task = dispatch(
                fs_publication_export,
                exclusive_resources=[exporter],
                kwargs={
                    "exporter_pk": exporter.pk,
                    "publication_pk": publication.pk,
                    "start_repo_version_pk": start_repository_version_pk,
                },
            )
        else:
            repo_version = self.get_resource(request.data["repository_version"], RepositoryVersion)

            task = dispatch(
                fs_repo_version_export,
                exclusive_resources=[exporter],
                kwargs={
                    "exporter_pk": str(exporter.pk),
                    "repo_version_pk": repo_version.pk,
                    "start_repo_version_pk": start_repository_version_pk,
                },
            )

        return OperationPostponedResponse(task, request)
