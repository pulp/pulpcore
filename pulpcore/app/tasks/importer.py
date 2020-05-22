import json
import os
import re
import tempfile
import tarfile
from gettext import gettext as _
from logging import getLogger

from django.conf import settings
from django.core.files.storage import default_storage
from pkg_resources import DistributionNotFound, get_distribution
from rest_framework.serializers import ValidationError
from tablib import Dataset

from pulpcore.app.apps import get_plugin_config
from pulpcore.app.models import (
    Artifact,
    Content,
    CreatedResource,
    PulpImport,
    PulpImporter,
    Repository,
    Task,
    TaskGroup,
)
from pulpcore.app.modelresource import (
    ArtifactResource,
    ContentArtifactResource,
    ContentResource,
)
from pulpcore.tasking.tasks import enqueue_with_reservation

log = getLogger(__name__)

ARTIFACT_FILE = "pulpcore.app.modelresource.ArtifactResource.json"
REPO_FILE = "pulpcore.app.modelresource.RepositoryResource.json"
CONTENT_FILE = "pulpcore.app.modelresource.ContentResource.json"
CA_FILE = "pulpcore.app.modelresource.ContentArtifactResource.json"
VERSIONS_FILE = "versions.json"


def _import_file(fpath, resource_class):
    log.info(_("Importing file {}.").format(fpath))
    with open(fpath, "r") as json_file:
        data = Dataset().load(json_file.read(), format="json")
        resource = resource_class()
        return resource.import_data(data, raise_errors=True)


def _repo_version_path(src_repo):
    """Find the repo version path in the export based on src_repo json."""
    src_repo_version = int(src_repo["next_version"]) - 1
    return f"repository-{src_repo['pulp_id']}_{src_repo_version}"


def _check_versions(version_json):
    """Compare the export version_json to the installed components."""
    error_messages = []
    for component in version_json:
        try:
            version = get_distribution(component["component"]).version
        except DistributionNotFound:
            error_messages.append(
                _("Export uses {} which is not installed.").format(component["component"])
            )
        else:
            if version != component["version"]:
                error_messages.append(
                    _(
                        "Export version {export_ver} of {component} does not match "
                        "installed version {ver}."
                    ).format(
                        export_ver=component["version"],
                        component=component["component"],
                        ver=version,
                    )
                )

        if error_messages:
            raise ValidationError((" ".join(error_messages)))


def import_repository_version(destination_repo_pk, source_repo_pk, tar_path):
    """
    Import a repository version from a Pulp export.

    Args:
        destination_repo_pk (str): Primary key of Repository to import into.
        source_repo_pk (str): Primary key of the Repository in the export.
        tar_path (str): A path to export tar.
    """
    dest_repo = Repository.objects.get(pk=destination_repo_pk)

    with tempfile.TemporaryDirectory() as temp_dir:
        # Extract the repo file for the repo info
        with tarfile.open(tar_path, "r:gz") as tar:
            tar.extract(REPO_FILE, path=temp_dir)

        with open(os.path.join(temp_dir, REPO_FILE), "r") as repo_data_file:
            data = json.load(repo_data_file)

        src_repo = next(repo for repo in data if repo["pulp_id"] == source_repo_pk)
        rv_path = os.path.join(temp_dir, _repo_version_path(src_repo))

        if dest_repo.pulp_type != src_repo["pulp_type"]:
            raise ValidationError(
                _(
                    "Repository type mismatch: {src_repo} ({src_type}) vs {dest_repo} "
                    "({dest_type})."
                ).format(
                    src_repo=src_repo["name"],
                    src_type=src_repo["pulp_type"],
                    dest_repo=dest_repo.name,
                    dest_type=dest_repo.pulp_type,
                )
            )

        # Extract the repo version files
        with tarfile.open(tar_path, "r:gz") as tar:
            for mem in tar.getmembers():
                if re.match(fr"^{_repo_version_path(src_repo)}/.+", mem.name):
                    tar.extract(mem, path=temp_dir)

        # Untyped Content
        content_path = os.path.join(rv_path, CONTENT_FILE)
        c_result = _import_file(content_path, ContentResource)
        content = Content.objects.filter(pk__in=[r.object_id for r in c_result.rows])

        # Content Artifacts
        ca_path = os.path.join(rv_path, CA_FILE)
        _import_file(ca_path, ContentArtifactResource)

        # Content
        plugin_name = src_repo["pulp_type"].split(".")[0]
        cfg = get_plugin_config(plugin_name)
        for res_class in cfg.exportable_classes:
            filename = f"{res_class.__module__}.{res_class.__name__}.json"
            _import_file(os.path.join(rv_path, filename), res_class)

        # Create the repo version
        with dest_repo.new_version() as new_version:
            new_version.set_content(content)


def pulp_import(importer_pk, path):
    """
    Import a Pulp export into Pulp.

    Args:
        importer_pk (str): Primary key of PulpImporter to do the import
        path (str): Path to the export to be imported
    """

    def destination_repo(source_repo_name):
        """Find the destination repository based on source repo's name."""
        if importer.repo_mapping and importer.repo_mapping.get(source_repo_name):
            dest_repo_name = importer.repo_mapping[source_repo_name]
        else:
            dest_repo_name = source_repo_name
        return Repository.objects.get(name=dest_repo_name)

    log.info(_("Importing {}.").format(path))
    importer = PulpImporter.objects.get(pk=importer_pk)
    pulp_import = PulpImport.objects.create(
        importer=importer, task=Task.current(), params={"path": path}
    )
    CreatedResource.objects.create(content_object=pulp_import)

    task_group = TaskGroup.objects.create(description=f"Import of {path}")
    CreatedResource.objects.create(content_object=task_group)

    with tempfile.TemporaryDirectory() as temp_dir:
        with tarfile.open(path, "r:gz") as tar:
            tar.extractall(path=temp_dir)

        # Check version info
        with open(os.path.join(temp_dir, VERSIONS_FILE)) as version_file:
            version_json = json.load(version_file)
            _check_versions(version_json)

        # Artifacts
        ar_result = _import_file(os.path.join(temp_dir, ARTIFACT_FILE), ArtifactResource)
        for row in ar_result.rows:
            artifact = Artifact.objects.get(pk=row.object_id)
            base_path = os.path.join("artifact", artifact.sha256[0:2], artifact.sha256[2:])
            src = os.path.join(temp_dir, base_path)
            dest = os.path.join(settings.MEDIA_ROOT, base_path)

            if not default_storage.exists(dest):
                with open(src, "rb") as f:
                    default_storage.save(dest, f)

        with open(os.path.join(temp_dir, REPO_FILE), "r") as repo_data_file:
            data = json.load(repo_data_file)

            for src_repo in data:
                try:
                    dest_repo = destination_repo(src_repo["name"])
                except Repository.DoesNotExist:
                    log.warn(
                        _("Could not find destination repo for {}. " "Skipping.").format(
                            src_repo["name"]
                        )
                    )
                    continue

                enqueue_with_reservation(
                    import_repository_version,
                    [dest_repo],
                    args=[dest_repo.pk, src_repo["pulp_id"], path],
                    task_group=task_group,
                )

    task_group.finish()
