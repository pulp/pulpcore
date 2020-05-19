import os
import io
import json
import tarfile
import tempfile

from django.conf import settings

from pulpcore.app.apps import get_plugin_config
from pulpcore.app.models.repository import Repository
from pulpcore.app.modelresource import (
    ArtifactResource,
    ContentResource,
    ContentArtifactResource,
    RepositoryResource,
)


def _write_export(the_tarfile, resource, dest_dir=None):
    """
    Write the JSON export for the specified resource to the specified tarfile.

    The resulting file will be found at <dest_dir>/<resource.__class__.__name__>.json. If dest_dir
    is None, the file will be added at the 'top level' of the_tarfile.

    Export-files are UTF-8 encoded.

    Args:
        the_tarfile (tarfile.Tarfile): tarfile we are writing into
        resource (import_export.resources.ModelResource): ModelResource to be exported
        dest_dir str(directory-path): directory 'inside' the tarfile to write to
    """
    filename = "{}.{}.json".format(resource.__module__, type(resource).__name__)
    dataset = resource.export(resource.queryset)
    if dest_dir:
        dest_filename = os.path.join(dest_dir, filename)
    else:
        dest_filename = filename

    data = dataset.json.encode("utf8")
    info = tarfile.TarInfo(name=dest_filename)
    info.size = len(data)
    the_tarfile.addfile(info, io.BytesIO(data))


def export_versions(export, version_info):
    """
    Write a JSON list of plugins and their versions as 'versions.json' to export.tarfile

    Output format is [{"component": "<pluginname>", "version": "<pluginversion>"},...]

    Args:
        export (django.db.models.PulpExport): export instance that's doing the export
        version_info (set): set of (distribution-label,version) tuples for repos in this export
    """
    # build the version-list from the distributions for each component
    versions = [{"component": label, "version": version} for (label, version) in version_info]

    version_json = json.dumps(versions).encode("utf8")
    info = tarfile.TarInfo(name="versions.json")
    info.size = len(version_json)
    export.tarfile.addfile(info, io.BytesIO(version_json))


def export_artifacts(export, artifacts):
    """
    Export a set of Artifacts, ArtifactResources, and RepositoryResources

    Args:
        export (django.db.models.PulpExport): export instance that's doing the export
        artifacts (django.db.models.Artifacts): list of artifacts in all repos being exported

    Raises:
        ValidationError: When path is not in the ALLOWED_EXPORT_PATHS setting
    """
    for artifact in artifacts:
        dest = artifact.file.name

        if settings.DEFAULT_FILE_STORAGE != "pulpcore.app.models.storage.FileSystem":
            with tempfile.TemporaryDirectory() as temp_dir:
                with tempfile.NamedTemporaryFile(dir=temp_dir) as temp_file:
                    temp_file.write(artifact.file.read())
                    temp_file.flush()
                    export.tarfile.add(temp_file.name, dest)
        else:
            export.tarfile.add(artifact.file.path, dest)

    resource = ArtifactResource()
    resource.queryset = artifacts
    _write_export(export.tarfile, resource)

    resource = RepositoryResource()
    resource.queryset = Repository.objects.filter(pk__in=export.exporter.repositories.all())
    _write_export(export.tarfile, resource)


def export_content(export, repository_version):
    """
    Export db-content, and the db-content of the owning repositories

    Args:
        export (django.db.models.PulpExport): export instance that's doing the export
        repository_version (django.db.models.RepositoryVersion): RepositoryVersion being exported
        last_export (django.db.models.PulpExport): previous export of the 'owning' Exporter
    """
    dest_dir = os.path.join(
        "repository-{}_{}".format(
            str(repository_version.repository.pulp_id), repository_version.number
        )
    )
    # export the resources pulpcore is responsible for
    resource = ContentResource(repository_version)
    _write_export(export.tarfile, resource, dest_dir)

    resource = ContentArtifactResource(repository_version)
    _write_export(export.tarfile, resource, dest_dir)

    # find and export any ModelResource found in pulp_<repo-type>.app.modelresource
    plugin_name = repository_version.repository.pulp_type.split(".")[0]
    cfg = get_plugin_config(plugin_name)
    if cfg.exportable_classes:
        for cls in cfg.exportable_classes:
            _write_export(export.tarfile, cls(repository_version), dest_dir)
