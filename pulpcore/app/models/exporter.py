import os
from gettext import gettext as _

from django.conf import settings
from django.db import models

from pulpcore.app.models import ContentArtifact, MasterModel


class FileSystemExporter(MasterModel):
    """
    A base class that provides logic to export a set of content. This set of content can be a
    publication, repo version, etc.

    Fields:

        name (models.TextField): The exporter unique name.
        path (models.TextField): a full path where the export will go.
    """

    name = models.TextField(db_index=True, unique=True)
    path = models.TextField()

    def _export_to_file_system(self, content_artifacts):
        """
        Export a set of ContentArtifacts to the filesystem.

        Args:
            content_artifacts (django.db.models.QuerySet): Set of ContentArtifacts to export
        """
        if content_artifacts.filter(artifact=None).exists():
            RuntimeError(_("Remote artifacts cannot be exported."))

        if settings.DEFAULT_FILE_STORAGE == 'pulpcore.app.models.storage.FileSystem':
            for ca in content_artifacts:
                artifact = ca.artifact
                src = os.path.join(settings.MEDIA_ROOT, artifact.file.name)
                dest = os.path.join(self.path, ca.relative_path)

                try:
                    os.makedirs(os.path.split(dest)[0])
                except FileExistsError:
                    pass

                os.link(src, dest)


class FileSystemPublicationExporter(FileSystemExporter):
    """
    A publication file system exporter.
    """

    def export(self, publication):
        """
        Export a publication to the file system

        Args:
            publication (pulpcore.app.models.Publication): a publication to export
        """
        content_artifacts = ContentArtifact.objects.filter(
            pk__in=publication.published_artifact.values_list("content_artifact__pk", flat=True))

        if publication.pass_through:
            content_artifacts |= ContentArtifact.objects.filter(
                content__in=publication.repository_version.content)

        self._export_to_file_system(content_artifacts)

    class Meta:
        abstract = True


class FileSystemRepositoryVersionExporter(FileSystemExporter):
    """
    A repo version file system exporter.
    """

    def export(self, repository_version):
        """
        Export a repository version to the file system

        Args:
            repository_version (pulpcore.app.models.RepositoryVersion): a repo version to export
        """
        content_artifacts = ContentArtifact.objects.filter(
            content__in=repository_version.content)

        self._export_to_file_system(content_artifacts)

    class Meta:
        abstract = True
