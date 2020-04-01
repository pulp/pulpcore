import os
from datetime import datetime
from gettext import gettext as _

from django.conf import settings
from django.contrib.postgres.fields import JSONField
from django.db import models

from pulpcore.app.models import (
    BaseModel,
    ContentArtifact,
    GenericRelationModel,
    MasterModel,
)
from .repository import Repository
from .task import CreatedResource, Task


class Export(BaseModel):
    """
    A class that represents an Export.

    Fields:

        params (models.JSONField): A set of parameters used to create the export

    Relations:

        task (models.ForeignKey): The Task that created the export
        exporter (models.ForeignKey): The Exporter that exported the resource.
    """
    params = JSONField(null=True)
    task = models.ForeignKey("Task", on_delete=models.PROTECT)
    exporter = models.ForeignKey("Exporter", on_delete=models.CASCADE)


class ExportedResource(GenericRelationModel):
    """
    A class to represent anything that was exported in an Export.

    Resource can be a repo version, publication, etc.

    Relations:

        export (models.ForeignKey): The Export that exported the resource.
    """
    export = models.ForeignKey(
        Export,
        related_name='exported_resources',
        on_delete=models.CASCADE
    )


class Exporter(MasterModel):
    """
    A base class that provides logic to export a set of content and keep track of Exports.

    Fields:

        name (models.TextField): The exporter unique name.
    """
    name = models.TextField(db_index=True, unique=True)


class FileSystemExporter(Exporter):
    """
    A base class that provides logic to export a set of content to the filesystem.

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
        from pulpcore.app.serializers import ExportSerializer
        ExportSerializer().validate_path(self.path)

        if content_artifacts.filter(artifact=None).exists():
            RuntimeError(_("Remote artifacts cannot be exported."))

        for ca in content_artifacts:
            artifact = ca.artifact
            dest = os.path.join(self.path, ca.relative_path)

            try:
                os.makedirs(os.path.split(dest)[0])
            except FileExistsError:
                pass

            if settings.DEFAULT_FILE_STORAGE == 'pulpcore.app.models.storage.FileSystem':
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
            pk__in=publication.published_artifact.values_list("content_artifact__pk", flat=True))

        if publication.pass_through:
            content_artifacts |= ContentArtifact.objects.filter(
                content__in=publication.repository_version.content)

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

        content_artifacts = ContentArtifact.objects.filter(
            content__in=repository_version.content)

        self._export_to_file_system(content_artifacts)

    class Meta:
        abstract = True


class PulpExport(Export):
    destination_dir = None

    def _export_artifacts(self, repository_version):
        """
        Export a set of Artifacts to the filesystem.

        Args:
            repository_version (django.db.models.RepositoryVersion): repo-version whose artifacts are to be exported

        Raises:
            ValidationError: When path is not in the ALLOWED_EXPORT_PATHS setting
        """
        import pydevd_pycharm
        pydevd_pycharm.settrace('192.168.1.109', port=3014, stdoutToServer=True, stderrToServer=True)
        content_artifacts = ContentArtifact.objects.filter(content__in=repository_version.content)
        if content_artifacts.filter(artifact=None).exists():
            RuntimeError(_("Remote artifacts cannot be exported."))

        for ca in content_artifacts:
            artifact = ca.artifact
            dest = os.path.join(self.destination_dir, artifact.file.name)

            try:
                os.makedirs(os.path.split(dest)[0])
            except FileExistsError:
                pass

            with open(dest, "wb") as f:
                f.write(artifact.file.read())

    def _export_content(self, repository_version):
        dest = os.path.join(self.destination_dir, 'repository-{}'.format(str(repository_version.pulp_id)))
        try:
            os.makedirs(dest)
        except FileExistsError:
            pass
        pass

    def export_repository_version(self, repository_version):
        """
        Export a repository version to the file system

        Args:
            repository_version (pulpcore.app.models.RepositoryVersion): a repo version to export
        """
        self._export_artifacts(repository_version)
        self._export_content(repository_version)


class PulpExporter(Exporter):
    """
    A class that provides exports that can be imported into other Pulp instances.

    Fields:

        path (models.TextField): a full path where the export will go.

    Relations:

        repositories (models.ManyToManyField): Repos to be exported.
        last_export (models.ForeignKey): The last Export from the Exporter.
    """
    TYPE = 'pulp'
    path = models.TextField()
    repositories = models.ManyToManyField(Repository)
    last_export = models.ForeignKey(PulpExport, on_delete=models.PROTECT, null=True)

    @staticmethod
    def _export_dir(export):
        # export-EXPORTID-YYYYMMDD_HHMM/
        return "export-{}-{}".format(str(export.pulp_id), datetime.utcnow().strftime("%Y%m%d_%H%M"))

    def pulp_export(self):
        import pydevd_pycharm
        pydevd_pycharm.settrace('192.168.1.109', port=3014, stdoutToServer=True, stderrToServer=True)

        repositories = self.repositories.all()
        export = PulpExport.objects.create(exporter=self, task=Task.current(), params=None)
        # TODO: 'soon' path will be a tarfile and we will be streaming directly into the tarfile
        export.destination_dir = os.path.join(self.path, self._export_dir(export))
        CreatedResource.objects.create(content_object=export)

        for repo in repositories:
            version = repo.latest_version()
            export.export_repository_version(version)
            ExportedResource.objects.create(export=export, content_object=version)

        self.last_export = export
        self.save()

    class Meta:
        default_related_name = '%(app_label)s_pulp_exporter'
