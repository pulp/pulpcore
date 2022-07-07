import hashlib
import json
import logging
import os
import subprocess
import tarfile

from distutils.util import strtobool
from gettext import gettext as _
from glob import glob
from pathlib import Path
from pkg_resources import get_distribution

from django.conf import settings

from pulpcore.app.models import (
    CreatedResource,
    ExportedResource,
    Exporter,
    FilesystemExport,
    Publication,
    PulpExport,
    PulpExporter,
    RepositoryVersion,
    Task,
)
from pulpcore.app.models.content import ContentArtifact
from pulpcore.app.serializers import PulpExportSerializer
from pulpcore.app.util import get_version_from_model
from pulpcore.app.importexport import (
    export_versions,
    export_artifacts,
    export_content,
)
from pulpcore.constants import FS_EXPORT_METHODS

log = logging.getLogger(__name__)


def _validate_fs_export(content_artifacts):
    """
    Args:
        content_artifacts (django.db.models.QuerySet): Set of ContentArtifacts to export

    Raises:
        RuntimeError: If Artifacts are not downloaded or when trying to link non-fs files
    """
    if content_artifacts.filter(artifact=None).exists():
        raise RuntimeError(_("Cannot export artifacts that haven't been downloaded."))


def _export_to_file_system(path, relative_paths_to_artifacts, method=FS_EXPORT_METHODS.WRITE):
    """
    Export a set of artifacts to the filesystem.

    Args:
        path (str): A path to export the ContentArtifacts to
        relative_paths_to_artifacts: A dict with {relative_path: artifact} mapping

    Raises:
        ValidationError: When path is not in the ALLOWED_EXPORT_PATHS setting
    """

    if (
        settings.DEFAULT_FILE_STORAGE != "pulpcore.app.models.storage.FileSystem"
        and method != FS_EXPORT_METHODS.WRITE
    ):
        raise RuntimeError(_("Only write is supported for non-filesystem storage."))

    for relative_path, artifact in relative_paths_to_artifacts.items():
        dest = os.path.join(path, relative_path)
        os.makedirs(os.path.split(dest)[0], exist_ok=True)

        if method == FS_EXPORT_METHODS.SYMLINK:
            src = os.path.join(settings.MEDIA_ROOT, artifact.file.name)
            os.symlink(src, dest)
        elif method == FS_EXPORT_METHODS.HARDLINK:
            src = os.path.join(settings.MEDIA_ROOT, artifact.file.name)
            os.link(src, dest)
        elif method == FS_EXPORT_METHODS.WRITE:
            with open(dest, "wb") as f, artifact.file as af:
                for chunk in af.chunks(1024 * 1024):
                    f.write(chunk)
        else:
            raise RuntimeError(_("Unsupported export method '{}'.").format(method))


def fs_publication_export(exporter_pk, publication_pk):
    """
    Export a publication to the file system.

    Args:
        exporter_pk (str): FilesystemExporter pk
        publication_pk (str): Publication pk
    """
    exporter = Exporter.objects.get(pk=exporter_pk).cast()
    publication = Publication.objects.get(pk=publication_pk).cast()
    export = FilesystemExport.objects.create(
        exporter=exporter,
        params={"publication": publication_pk},
        task=Task.current(),
    )
    ExportedResource.objects.create(export=export, content_object=publication)
    CreatedResource.objects.create(content_object=export)

    log.info(
        _(
            "Exporting: file_system_exporter={exporter}, publication={publication}, path=path"
        ).format(exporter=exporter.name, publication=publication.pk, path=exporter.path)
    )

    content_artifacts = ContentArtifact.objects.filter(
        pk__in=publication.published_artifact.values_list("content_artifact__pk", flat=True)
    )

    if publication.pass_through:
        content_artifacts |= ContentArtifact.objects.filter(
            content__in=publication.repository_version.content
        )

    _validate_fs_export(content_artifacts)

    relative_path_to_artifacts = {}
    if publication.pass_through:
        relative_path_to_artifacts = {
            ca.relative_path: ca.artifact
            for ca in content_artifacts.select_related("artifact").iterator()
        }

    for pa in publication.published_artifact.select_related(
        "content_artifact", "content_artifact__artifact"
    ).iterator():
        relative_path_to_artifacts[pa.relative_path] = pa.content_artifact.artifact

    _export_to_file_system(exporter.path, relative_path_to_artifacts, exporter.method)


def fs_repo_version_export(exporter_pk, repo_version_pk):
    """
    Export a repository version to the file system.

    Args:
        exporter_pk (str): FilesystemExporter pk
        repo_version_pk (str): RepositoryVersion pk
    """
    exporter = Exporter.objects.get(pk=exporter_pk).cast()
    repo_version = RepositoryVersion.objects.get(pk=repo_version_pk)
    export = FilesystemExport.objects.create(
        exporter=exporter,
        params={"repository_version": repo_version_pk},
        task=Task.current(),
    )
    ExportedResource.objects.create(export=export, content_object=repo_version)
    CreatedResource.objects.create(content_object=export)

    log.info(
        _(
            "Exporting: file_system_exporter={exporter}, repo_version={repo_version}, path=path"
        ).format(exporter=exporter.name, repo_version=repo_version.pk, path=exporter.path)
    )

    content_artifacts = ContentArtifact.objects.filter(content__in=repo_version.content)
    _validate_fs_export(content_artifacts)

    relative_path_to_artifacts = {
        ca.relative_path: ca.artifact
        for ca in content_artifacts.select_related("artifact").iterator()
    }

    _export_to_file_system(exporter.path, relative_path_to_artifacts, exporter.method)


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


def _get_starting_versions(do_incremental, the_exporter, the_export):
    # list-of-previous-versions, or None
    if do_incremental:
        if the_export.validated_start_versions:
            prev_versions = the_export.validated_start_versions
        else:
            prev_versions = [
                er.content_object
                for er in ExportedResource.objects.filter(export=the_exporter.last_export).all()
            ]
    else:
        prev_versions = None
    return prev_versions


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
    full = the_export.params.get("full", True)
    if isinstance(full, str):
        full = bool(strtobool(full))
    starting_versions_provided = len(the_export.params.get("start_versions", [])) > 0
    last_exists = the_exporter.last_export
    return (starting_versions_provided or last_exists) and not full


def pulp_export(exporter_pk, params):
    """
    Create a PulpExport to export pulp_exporter.repositories.

    1) Spit out all Artifacts, ArtifactResource.json, and RepositoryResource.json
    2) Spit out all *resource JSONs in per-repo-version directories
    3) Compute and store the sha256 and filename of the resulting tar.gz/chunks

    Args:
        exporter_pk (str): PulpExporter
        params (dict): request data

    Raises:
        ValidationError: When path is not in the ALLOWED_EXPORT_PATHS setting,
            OR path exists and is not a directory
    """
    pulp_exporter = PulpExporter.objects.get(pk=exporter_pk)
    serializer = PulpExportSerializer(data=params, context={"exporter": pulp_exporter})
    serializer.is_valid(raise_exception=True)
    the_export = PulpExport.objects.create(exporter=pulp_exporter, params=params)
    the_export.validated_versions = serializer.validated_data.get("versions", None)
    the_export.validated_start_versions = serializer.validated_data.get("start_versions", None)
    the_export.validated_chunk_size = serializer.validated_data.get("chunk_size", None)

    try:
        the_export.task = Task.current()

        tarfile_fp = the_export.export_tarfile_path()

        path = Path(pulp_exporter.path)
        if not path.is_dir():
            path.mkdir(mode=0o775, parents=True)

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
                try:
                    with tarfile.open(tarfile_fp, "w|gz", fileobj=split_process.stdin) as tar:
                        _do_export(pulp_exporter, tar, the_export)
                except Exception:
                    # no matter what went wrong, we can't trust the files we (may have) created.
                    # Delete the ones we can find and pass the problem up.
                    for pathname in glob(tarfile_fp + ".*"):
                        os.remove(pathname)
                    raise
            # compute the hashes
            global_hash = hashlib.sha256()
            paths = sorted([str(Path(p)) for p in glob(tarfile_fp + ".*")])
            for a_file in paths:
                a_hash = _compute_hash(a_file, global_hash)
                rslts[a_file] = a_hash
            tarfile_hash = global_hash.hexdigest()

        else:
            # write into the file
            try:
                with tarfile.open(tarfile_fp, "w:gz") as tar:
                    _do_export(pulp_exporter, tar, the_export)
            except Exception:
                # no matter what went wrong, we can't trust the file we created.
                # Delete it if it exists and pass the problem up.
                if os.path.exists(tarfile_fp):
                    os.remove(tarfile_fp)
                raise
            # compute the hash
            tarfile_hash = _compute_hash(tarfile_fp)
            rslts[tarfile_fp] = tarfile_hash

        # store the outputfile/hash info
        the_export.output_file_info = rslts

        # write outputfile/hash info to a file 'next to' the output file(s)
        output_file_info_path = tarfile_fp.replace(".tar.gz", "-toc.json")
        with open(output_file_info_path, "w") as outfile:
            if the_export.validated_chunk_size:
                chunk_size = the_export.validated_chunk_size
            else:
                chunk_size = 0
            chunk_toc = {
                "meta": {
                    "chunk_size": chunk_size,
                    "file": os.path.basename(tarfile_fp),
                    "global_hash": tarfile_hash,
                },
                "files": {},
            }
            # Build a toc with just filenames (not the path on the exporter-machine)
            for a_path in rslts.keys():
                chunk_toc["files"][os.path.basename(a_path)] = rslts[a_path]
            json.dump(chunk_toc, outfile)

        # store toc info
        toc_hash = _compute_hash(output_file_info_path)
        the_export.output_file_info[output_file_info_path] = toc_hash
        the_export.toc_info = {"file": output_file_info_path, "sha256": toc_hash}
    finally:
        # whatever may have happened, make sure we save the export
        the_export.save()

    # If an exception was thrown, we'll never get here - which is good, because we don't want a
    # 'failed' export to be the last_export we derive the next incremental from
    # mark it as 'last'
    pulp_exporter.last_export = the_export
    # save the exporter
    pulp_exporter.save()


def _compute_hash(filename, global_hash=None):
    sha256_hash = hashlib.sha256()
    with open(filename, "rb") as f:
        # Read and update hash string value in blocks of 4K
        for byte_block in iter(lambda: f.read(4096), b""):
            sha256_hash.update(byte_block)
            if global_hash:
                global_hash.update(byte_block)
        return sha256_hash.hexdigest()


def _do_export(pulp_exporter, tar, the_export):
    the_export.tarfile = tar
    CreatedResource.objects.create(content_object=the_export)
    ending_versions = _get_versions_to_export(pulp_exporter, the_export)
    plugin_version_info = _get_versions_info(pulp_exporter)
    do_incremental = _incremental_requested(the_export)
    starting_versions = _get_starting_versions(do_incremental, pulp_exporter, the_export)
    vers_match = _version_match(ending_versions, starting_versions)
    # Gather up versions and artifacts
    artifacts = []
    for version in ending_versions:
        # Check version-content to make sure we're not being asked to export
        # an on_demand repo
        content_artifacts = ContentArtifact.objects.filter(content__in=version.content)
        if content_artifacts.filter(artifact=None).exists():
            raise RuntimeError(_("Remote artifacts cannot be exported."))

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
    for version in ending_versions:
        export_content(the_export, version)
        ExportedResource.objects.create(export=the_export, content_object=version)
