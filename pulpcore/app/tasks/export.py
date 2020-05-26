import hashlib
import logging
import os
import subprocess
import tarfile

from distutils.util import strtobool
from gettext import gettext as _
from glob import glob
from pathlib import Path
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
        exporter_pk (str): FilesystemExporter pk
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
        exporter_pk (str): FilesystemExporter pk
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


def _version_match(curr_versions, prev_versions):
    """
    Match list of repo-versions, to a prev-set, based on belonging to the same repository.

    We need this in order to be able to know how to 'diff' versions for incremental exports.

    :param curr_versions ([model.RepositoryVersion]): versions we want to export
    :param prev_versions ([model.RepositoryVersion]): last set of versions we exported (if any)
    :return: { <a_curr_version>: <matching-prev-version>, or None if no match or no prev_versions }
    """
    curr_to_repo = {v.repository: v for v in curr_versions}
    if prev_versions is None:
        return {curr_to_repo[repo]: None for repo in curr_to_repo}
    else:
        prev_to_repo = {v.repository: v for v in prev_versions}
        return {curr_to_repo[repo]: prev_to_repo[repo] for repo in curr_to_repo}


def _incremental_requested(the_export):
    """Figure out that a) an incremental is requested, and b) it's possible."""
    the_exporter = the_export.exporter
    params = the_export.params
    full = bool(strtobool(params["full"])) if "full" in params else True
    last_exists = the_exporter.last_export
    return last_exists and not full


def pulp_export(the_export):
    """
    Create a PulpExport to export pulp_exporter.repositories.

    1) Spit out all Artifacts, ArtifactResource.json, and RepositoryResource.json
    2) Spit out all *resource JSONs in per-repo-version directories
    3) Compute and store the sha256 and filename of the resulting tar.gz/chunks

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
    rslts = {}

    if the_export.validated_chunk_size:
        # write it into chunks
        with subprocess.Popen(
            [
                "split",
                "-a",
                "4",
                "-b",
                str(the_export.validated_chunk_size),
                "-d",
                "-",
                tarfile_fp + ".",
            ],
            stdin=subprocess.PIPE,
        ) as split_process:
            with tarfile.open(tarfile_fp, "w|gz", fileobj=split_process.stdin) as tar:
                _do_export(pulp_exporter, tar, the_export)

        # compute the hashes
        paths = [str(Path(p)) for p in glob(tarfile_fp + ".*")]
        for a_file in paths:
            a_hash = _compute_hash(a_file)
            rslts[a_file] = a_hash
    else:
        # write into the file
        with tarfile.open(tarfile_fp, "w:gz") as tar:
            _do_export(pulp_exporter, tar, the_export)
        # compute the hash
        tarfile_hash = _compute_hash(tarfile_fp)
        rslts[tarfile_fp] = tarfile_hash

    # store the outputfile/hash info
    the_export.output_file_info = rslts
    # save the export
    the_export.save()
    # mark it as 'last'
    pulp_exporter.last_export = the_export
    # save the exporter
    pulp_exporter.save()


def _compute_hash(filename):
    sha256_hash = hashlib.sha256()
    with open(filename, "rb") as f:
        # Read and update hash string value in blocks of 4K
        for byte_block in iter(lambda: f.read(4096), b""):
            sha256_hash.update(byte_block)
        return sha256_hash.hexdigest()


def _do_export(pulp_exporter, tar, the_export):
    the_export.tarfile = tar
    CreatedResource.objects.create(content_object=the_export)
    versions_to_export = _get_versions_to_export(pulp_exporter, the_export)
    plugin_version_info = _get_versions_info(pulp_exporter)
    do_incremental = _incremental_requested(the_export)
    # list-of-previous-versions, or None
    if do_incremental:
        prev_versions = [
            er.content_object
            for er in ExportedResource.objects.filter(export=pulp_exporter.last_export).all()
        ]
    else:
        prev_versions = None
    vers_match = _version_match(versions_to_export, prev_versions)
    # Gather up versions and artifacts
    artifacts = []
    for version in versions_to_export:
        # Check version-content to make sure we're not being asked to export
        # an on_demand repo
        content_artifacts = ContentArtifact.objects.filter(content__in=version.content)
        if content_artifacts.filter(artifact=None).exists():
            RuntimeError(_("Remote artifacts cannot be exported."))

        if do_incremental:
            vers_artifacts = version.artifacts.difference(vers_match[version].artifacts).all()
        else:
            vers_artifacts = version.artifacts.all()
        artifacts.extend(vers_artifacts)
    # export plugin-version-info
    export_versions(the_export, plugin_version_info)
    # Export the top-level entities (artifacts and repositories)
    # Note: we've already handled "what about incrementals" when building the 'artifacts' list
    export_artifacts(the_export, artifacts)
    # Export the repository-version data, per-version
    for version in versions_to_export:
        export_content(the_export, version)
        ExportedResource.objects.create(export=the_export, content_object=version)
