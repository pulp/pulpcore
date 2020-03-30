import json
import os
import tempfile
import tarfile
from gettext import gettext as _
from logging import getLogger

from django.conf import settings
from django.core.files.storage import default_storage
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
)
from pulpcore.app.modelresource import (
    ArtifactResource,
    ContentArtifactResource,
    ContentResource,
)

log = getLogger(__name__)

ARTIFACT_FILE = "pulpcore.app.modelresource.ArtifactResource.json"
REPO_FILE = "pulpcore.app.modelresource.RepositoryResource.json"
CONTENT_FILE = "pulpcore.app.modelresource.ContentResource.json"
CA_FILE = "pulpcore.app.modelresource.ContentArtifactResource.json"


def pulp_import(importer_pk, path):
    """
    Import a Pulp export into Pulp.

    Args:
        importer_pk (str): Primary key of PulpImporter to do the import
        path (str): Path to the export to be imported
    """
    def import_file(fpath, resource_class):
        log.info(_("Importing file {}.").format(fpath))
        with open(fpath, "r") as json_file:
            data = Dataset().load(json_file.read(), format="json")
            resource = resource_class()
            return resource.import_data(data, raise_errors=True)

    def destination_repo(source_repo_name):
        """Find the destination repository based on source repo's name."""
        if importer.repo_mapping and importer.repo_mapping.get(source_repo_name):
            dest_repo_name = importer.repo_mapping[source_repo_name]
        else:
            dest_repo_name = source_repo_name
        return Repository.objects.get(name=dest_repo_name)

    def repo_version_path(temp_dir, src_repo):
        """Find the repo version path in the export based on src_repo json."""
        src_repo_version = int(src_repo["next_version"]) - 1
        return os.path.join(temp_dir, f"repository-{src_repo['pulp_id']}_{src_repo_version}")

    log.info(_("Importing {}.").format(path))
    importer = PulpImporter.objects.get(pk=importer_pk)
    pulp_import = PulpImport.objects.create(importer=importer,
                                            task=Task.current(),
                                            params={"path": path})
    CreatedResource.objects.create(content_object=pulp_import)

    with tempfile.TemporaryDirectory() as temp_dir:
        with tarfile.open(path, "r|gz") as tar:
            tar.extractall(path=temp_dir)

        # Artifacts
        ar_result = import_file(os.path.join(temp_dir, ARTIFACT_FILE), ArtifactResource)
        for row in ar_result.rows:
            artifact = Artifact.objects.get(pk=row.object_id)
            base_path = os.path.join('artifact', artifact.sha256[0:2], artifact.sha256[2:])
            src = os.path.join(temp_dir, base_path)
            dest = os.path.join(settings.MEDIA_ROOT, base_path)

            if not default_storage.exists(dest):
                with open(src, 'rb') as f:
                    default_storage.save(dest, f)

        # Repo Versions
        with open(os.path.join(temp_dir, REPO_FILE), "r") as repo_data_file:
            data = json.load(repo_data_file)

            for src_repo in data:
                try:
                    dest_repo = destination_repo(src_repo["name"])
                except Repository.DoesNotExist:
                    log.warn(_("Could not find destination repo for {}. "
                               "Skipping.").format(src_repo["name"]))
                    continue

                rv_path = repo_version_path(temp_dir, src_repo)

                # Untyped Content
                content_path = os.path.join(rv_path, CONTENT_FILE)
                c_result = import_file(content_path, ContentResource)
                content = Content.objects.filter(pk__in=[r.object_id for r in c_result.rows])

                # Content Artifacts
                ca_path = os.path.join(rv_path, CA_FILE)
                import_file(ca_path, ContentArtifactResource)

                # Content
                plugin_name = src_repo["pulp_type"].split('.')[0]
                cfg = get_plugin_config(plugin_name)
                for res_class in cfg.exportable_classes:
                    filename = f"{res_class.__module__}.{res_class.__name__}.json"
                    import_file(os.path.join(rv_path, filename), res_class)

                # Create the repo version
                with dest_repo.new_version() as new_version:
                    new_version.set_content(content)

    return importer
