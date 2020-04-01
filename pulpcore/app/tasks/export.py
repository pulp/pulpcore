import hashlib
import logging
import os
import tarfile

from gettext import gettext as _

from pulpcore.app.models import (
    CreatedResource,
    ExportedResource,
    Exporter,
    Publication,
    PulpExport,
    RepositoryVersion,
    Task,
)
from pulpcore.app.models.content import (
    ContentArtifact,
)

log = logging.getLogger(__name__)


def fs_publication_export(exporter_pk, publication_pk):
    """
    Export a publication to the file system.

    Args:
        exporter_pk (str): FileSystemExporter pk
        publication_pk (str): Publication pk
    """
    exporter = Exporter.objects.get(pk=exporter_pk).cast()
    publication = Publication.objects.get(pk=publication_pk).cast()

    log.info(
        _(
            "Exporting: file_system_exporter={exporter}, publication={publication}, path=path"
        ).format(exporter=exporter.name, publication=publication.pk, path=exporter.path)
    )
    exporter.export_publication(publication)


def fs_repo_version_export(exporter_pk, repo_version_pk):
    """
    Export a repository version to the file system.

    Args:
        exporter_pk (str): FileSystemExporter pk
        repo_version_pk (str): RepositoryVersion pk
    """
    exporter = Exporter.objects.get(pk=exporter_pk).cast()
    repo_version = RepositoryVersion.objects.get(pk=repo_version_pk)

    log.info(
        _(
            "Exporting: file_system_exporter={exporter}, repo_version={repo_version}, path=path"
        ).format(exporter=exporter.name, repo_version=repo_version.pk, path=exporter.path)
    )
    exporter.export_repository_version(repo_version)


def pulp_export(pulp_exporter):
    """
    Create a PulpExport to export pulp_exporter.repositories

    1) Spit out all Artifacts, ArtifactResource.json, and RepositoryResource.json
    2) Spit out all *resource JSONs in per-repo-version directories
    3) Compute and store the sha256 and filename of the resulting tar.gz

    Args:
        pulp_exporter (models.PulpExporter): PulpExporter instance

    Raises:
        ValidationError: When path is not in the ALLOWED_EXPORT_PATHS setting,
            OR path exists and is not a directory
    """

    from pulpcore.app.serializers.exporter import ExporterSerializer
    ExporterSerializer.validate_path(pulp_exporter.path, check_is_dir=True)

    repositories = pulp_exporter.repositories.all()
    export = PulpExport.objects.create(exporter=pulp_exporter, task=Task.current(), params=None)
    tarfile_fp = export.export_tarfile_path()
    os.makedirs(pulp_exporter.path, exist_ok=True)

    with tarfile.open(tarfile_fp, 'w:gz') as tar:
        export.tarfile = tar
        CreatedResource.objects.create(content_object=export)

        artifacts = []
        repo_versions = []
        # Gather up the versions and artifacts
        for repo in repositories:
            version = repo.latest_version()
            # Check version-content to make sure we're not being asked to export an on_demand repo
            content_artifacts = ContentArtifact.objects.filter(content__in=version.content)
            if content_artifacts.filter(artifact=None).exists():
                RuntimeError(_("Remote artifacts cannot be exported."))

            repo_versions.append(version)
            artifacts.extend(version.artifacts.all())

        from pulpcore.app.importexport import export_artifacts, export_content
        # Export the top-level entities (artifacts and repositories)
        export_artifacts(export, artifacts, pulp_exporter.last_export)
        # Export the repository-version data, per-version
        for version in repo_versions:
            export_content(export, version, pulp_exporter.last_export)
            ExportedResource.objects.create(export=export, content_object=version)

    sha256_hash = hashlib.sha256()
    with open(tarfile_fp, "rb") as f:
        # Read and update hash string value in blocks of 4K
        for byte_block in iter(lambda: f.read(4096), b""):
            sha256_hash.update(byte_block)
        export.sha256 = sha256_hash.hexdigest()
    export.filename = tarfile_fp
    export.save()
    pulp_exporter.last_export = export
    pulp_exporter.save()
