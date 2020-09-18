import os
from datetime import datetime
from gettext import gettext as _

from django.conf import settings
from django.contrib.postgres.fields import JSONField
from django.db import models

from pulpcore.app.models import (
    BaseModel,
    GenericRelationModel,
    MasterModel,
)

from .task import CreatedResource, Task

from pulpcore.app.models.content import ContentArtifact
from pulpcore.app.models.repository import Repository


class Export(BaseModel):
    """
    A model that represents an Export.

    Fields:

        params (models.JSONField): A set of parameters used to create the export

    Relations:

        task (models.ForeignKey): The Task that created the export
        exporter (models.ForeignKey): The Exporter that exported the resource.
    """

    params = JSONField(null=True)
    task = models.ForeignKey("Task", on_delete=models.PROTECT, null=True)
    exporter = models.ForeignKey("Exporter", on_delete=models.CASCADE)


class ExportedResource(GenericRelationModel):
    """
    A model to represent anything that was exported in an Export.

    Resource can be a repo version, publication, etc.

    Relations:

        export (models.ForeignKey): The Export that exported the resource.
    """

    export = models.ForeignKey(Export, related_name="exported_resources", on_delete=models.CASCADE)


class Exporter(MasterModel):
    """
    A base model that provides logic to export a set of content and keep track of Exports.

    Fields:

        name (models.TextField): The exporter unique name.
    """

    name = models.TextField(db_index=True, unique=True)


class FilesystemExporter(Exporter):
    """
    A base model that provides logic to export a set of content to the filesystem.

    Fields:

        path (models.TextField): a full path where the export will go.
    """

    path = models.TextField()

    def _export_to_file_system(self, content_artifacts):
        """
        Export a set of ContentArtifacts to the filesystem.

        Args:
            content_artifacts (django.db.models.QuerySet): Set of ContentArtifacts to export

        Raises:
            ValidationError: When path is not in the ALLOWED_EXPORT_PATHS setting
        """
        if content_artifacts.filter(artifact=None).exists():
            RuntimeError(_("Remote artifacts cannot be exported."))

        for ca in content_artifacts:
            artifact = ca.artifact
            dest = os.path.join(self.path, ca.relative_path)

            try:
                os.makedirs(os.path.split(dest)[0])
            except FileExistsError:
                pass

            if settings.DEFAULT_FILE_STORAGE == "pulpcore.app.models.storage.FileSystem":
                src = os.path.join(settings.MEDIA_ROOT, artifact.file.name)
                os.link(src, dest)
            else:
                with open(dest, "wb") as f:
                    f.write(artifact.file.read())

    def export_publication(self, publication):
        """
        Export a publication to the file system

        Args:
            publication (pulpcore.app.models.Publication): a publication to export
        """
        export = Export.objects.create(exporter=self, task=Task.current())
        ExportedResource.objects.create(export=export, content_object=publication)
        CreatedResource.objects.create(content_object=export)

        content_artifacts = ContentArtifact.objects.filter(
            pk__in=publication.published_artifact.values_list("content_artifact__pk", flat=True)
        )

        if publication.pass_through:
            content_artifacts |= ContentArtifact.objects.filter(
                content__in=publication.repository_version.content
            )

        self._export_to_file_system(content_artifacts)

    def export_repository_version(self, repository_version):
        """
        Export a repository version to the file system

        Args:
            repository_version (pulpcore.app.models.RepositoryVersion): a repo version to export
        """
        export = Export.objects.create(exporter=self, task=Task.current())
        ExportedResource.objects.create(export=export, content_object=repository_version)
        CreatedResource.objects.create(content_object=export)

        content_artifacts = ContentArtifact.objects.filter(content__in=repository_version.content)

        self._export_to_file_system(content_artifacts)

    class Meta:
        abstract = True


class PulpExport(Export):
    """
    A model that provides export-files that can be imported into other Pulp instances.

    Fields:

        tarfile (tarfile.Tarfile): a tarfile for this export to write into.
        validated_versions ([pulpcore.app.models.RepositoryVersion]): explicitly-specified versions
            to be exported (if any).
        validated_start_versions ([pulpcore.app.models.RepositoryVersion]): explicitly-specified
            starting-versions for doing an incremental export.
        validated_chunk_size (str) : requested chunk-size of the export file.
        output_file_info (models.JSONField) : JSON containing the full-path filenames and
            SHA256-checksums of all output-files generated by this export.
        toc_info (models.JSONField) : JSON containing the full-path filename and SHA256-checksum
            of the table-of-contents for this export.
    """

    tarfile = None
    validated_versions = None
    validated_start_versions = None
    validated_chunk_size = None
    output_file_info = JSONField(null=True)
    toc_info = JSONField(null=True)

    def export_tarfile_path(self):
        """
        Return the full tarfile name where the specified PulpExport should store its export
        """
        # EXPORTER-PATH/export-EXPORTID-YYYYMMDD_HHMM.tar.gz
        return os.path.normpath(
            "{}/export-{}-{}.tar.gz".format(
                self.exporter.path, str(self.pulp_id), datetime.utcnow().strftime("%Y%m%d_%H%M")
            )
        )

    class Meta:
        default_related_name = "%(app_label)s_pulp_export"


class PulpExporter(Exporter):
    """
    A model that controls creating exports that can be imported into other Pulp instances.

    Fields:

        path (models.TextField): a full path where the export will go.

    Relations:

        repositories (models.ManyToManyField): Repos to be exported.
        last_export (models.ForeignKey): The last Export from the Exporter.
    """

    TYPE = "pulp"
    path = models.TextField()
    repositories = models.ManyToManyField(Repository)
    last_export = models.ForeignKey(
        "PulpExport", related_name="last_export", on_delete=models.SET_NULL, null=True
    )

    class Meta:
        default_related_name = "%(app_label)s_pulp_exporter"
