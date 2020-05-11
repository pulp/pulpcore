import hashlib
import logging
import os
import tarfile

from gettext import gettext as _
from pkg_resources import get_distribution

from pulpcore.app.models import (
    CreatedResource,
    ExportedResource,
    Exporter,
    Publication,
    RepositoryVersion,
    Task,
)
from pulpcore.app.models.content import ContentArtifact
from pulpcore.app.util import get_version_from_model
from pulpcore.app.importexport import (
    export_versions,
    export_artifacts,
    export_content,
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


def _get_versions_to_export(the_exporter, the_export):
    """
    Return repo-versions to be exported.

    versions is based on exporter-repositories and how the export-cmd was
    invoked.
    """
    repositories = the_exporter.repositories.all()
    # Figure out which RepositoryVersions we're going to be exporting
    # Use repo.latest unless versions= was specified
    if the_export.validated_versions is not None:
        versions = the_export.validated_versions
    else:
        versions = [r.latest_version() for r in repositories]
    return versions


def _get_versions_info(the_exporter):
    """
    Return plugin-version-info based on plugins are responsible for exporter-repositories.
    """
    repositories = the_exporter.repositories.all()

    # extract plugin-version-info based on the repositories we're exporting from
    vers_info = set()
    # We always need to know what version of pulpcore was in place
    vers_info.add(("pulpcore", get_distribution("pulpcore").version))
    # for each repository being exported, get the version-info for the plugin that
    # owns/controls that kind-of repository
    for r in repositories:
        vers_info.add(get_version_from_model(r.cast()))

    return vers_info


def pulp_export(the_export):
    """
    Create a PulpExport to export pulp_exporter.repositories.

    1) Spit out all Artifacts, ArtifactResource.json, and RepositoryResource.json
    2) Spit out all *resource JSONs in per-repo-version directories
    3) Compute and store the sha256 and filename of the resulting tar.gz

    Args:
        the_export (models.PulpExport): PulpExport instance

    Raises:
        ValidationError: When path is not in the ALLOWED_EXPORT_PATHS setting,
            OR path exists and is not a directory
    """
    pulp_exporter = the_export.exporter
    the_export.task = Task.current()

    tarfile_fp = the_export.export_tarfile_path()
    os.makedirs(pulp_exporter.path, exist_ok=True)

    with tarfile.open(tarfile_fp, "w:gz") as tar:
        the_export.tarfile = tar
        CreatedResource.objects.create(content_object=the_export)
        versions_to_export = _get_versions_to_export(pulp_exporter, the_export)
        plugin_version_info = _get_versions_info(pulp_exporter)

        # Gather up versions and artifacts
        artifacts = []
        for version in versions_to_export:
            # Check version-content to make sure we're not being asked to export an on_demand repo
            content_artifacts = ContentArtifact.objects.filter(content__in=version.content)
            if content_artifacts.filter(artifact=None).exists():
                RuntimeError(_("Remote artifacts cannot be exported."))
            artifacts.extend(version.artifacts.all())

        # export plugin-version-info
        export_versions(the_export, plugin_version_info)
        # Export the top-level entities (artifacts and repositories)
        export_artifacts(the_export, artifacts, pulp_exporter.last_export)
        # Export the repository-version data, per-version
        for version in versions_to_export:
            export_content(the_export, version, pulp_exporter.last_export)
            ExportedResource.objects.create(export=the_export, content_object=version)

    sha256_hash = hashlib.sha256()
    with open(tarfile_fp, "rb") as f:
        # Read and update hash string value in blocks of 4K
        for byte_block in iter(lambda: f.read(4096), b""):
            sha256_hash.update(byte_block)
        the_export.sha256 = sha256_hash.hexdigest()
    the_export.filename = tarfile_fp
    the_export.save()
    pulp_exporter.last_export = the_export
    pulp_exporter.save()
