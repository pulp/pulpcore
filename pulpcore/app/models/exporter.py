import os
from datetime import datetime

from django.db import models

from pulpcore.app.models import (
    BaseModel,
    GenericRelationModel,
    MasterModel,
)
from pulpcore.app.models.repository import Repository
from pulpcore.constants import FS_EXPORT_CHOICES, FS_EXPORT_METHODS


class Export(BaseModel):
    """
    A model that represents an Export.

    Fields:

        params (models.JSONField): A set of parameters used to create the export

    Relations:

        task (models.ForeignKey): The Task that created the export
        exporter (models.ForeignKey): The Exporter that exported the resource.
    """

    params = models.JSONField(null=True)
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


class FilesystemExport(Export):
    """
    A model that represents an export to the filesystem.
    """

    pass


class FilesystemExporter(Exporter):
    """
    A base model that provides logic to export a set of content to the filesystem.

    Fields:

        path (models.TextField): a full path where the export will go.
    """

    TYPE = "filesystem"

    path = models.TextField()
    method = models.CharField(
        choices=FS_EXPORT_CHOICES, default=FS_EXPORT_METHODS.WRITE, max_length=128
    )

    class Meta:
        default_related_name = "%(app_label)s_fs_exporter"


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
    output_file_info = models.JSONField(null=True)
    toc_info = models.JSONField(null=True)

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
