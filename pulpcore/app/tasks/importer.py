import hashlib
import json
import os
import re
import subprocess
import tempfile
import tarfile
from gettext import gettext as _
from logging import getLogger

from django.conf import settings
from django.core.files.storage import default_storage
from django.db.models import F

from pkg_resources import DistributionNotFound, get_distribution
from rest_framework.serializers import ValidationError
from tablib import Dataset

from pulpcore.app.apps import get_plugin_config
from pulpcore.app.models import (
    Artifact,
    Content,
    CreatedResource,
    GroupProgressReport,
    ProgressReport,
    PulpImport,
    PulpImporter,
    Repository,
    Task,
    TaskGroup,
)
from pulpcore.app.modelresource import (
    ArtifactResource,
    ContentArtifactResource,
)
from pulpcore.constants import TASK_STATES
from pulpcore.tasking.tasks import dispatch

log = getLogger(__name__)

ARTIFACT_FILE = "pulpcore.app.modelresource.ArtifactResource.json"
REPO_FILE = "pulpcore.app.modelresource.RepositoryResource.json"
CONTENT_FILE = "pulpcore.app.modelresource.ContentResource.json"
CA_FILE = "pulpcore.app.modelresource.ContentArtifactResource.json"
VERSIONS_FILE = "versions.json"
CONTENT_MAPPING_FILE = "content_mapping.json"


def _destination_repo(importer, source_repo_name):
    """Find the destination repository based on source repo's name."""
    if importer.repo_mapping and importer.repo_mapping.get(source_repo_name):
        dest_repo_name = importer.repo_mapping[source_repo_name]
    else:
        dest_repo_name = source_repo_name
    return Repository.objects.get(name=dest_repo_name)


def _import_file(fpath, resource_class, do_raise=True):
    try:
        log.info(_("Importing file {}.").format(fpath))
        with open(fpath, "r") as json_file:
            data = Dataset().load(json_file.read(), format="json")
            resource = resource_class()
            log.info(_("...Importing resource {}.").format(resource.__class__.__name__))
            return resource.import_data(data, raise_errors=do_raise)
    except AttributeError:
        log.error(_("FAILURE importing file {}!").format(fpath))
        raise


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


def import_repository_version(importer_pk, destination_repo_pk, source_repo_name, tar_path):
    """
    Import a repository version from a Pulp export.

    Args:
        importer_pk (str): Importer we are working with
        destination_repo_pk (str): Primary key of Repository to import into.
        source_repo_name (str): Name of the Repository in the export.
        tar_path (str): A path to export tar.
    """
    dest_repo = Repository.objects.get(pk=destination_repo_pk)
    importer = PulpImporter.objects.get(pk=importer_pk)

    pb = ProgressReport(
        message=f"Importing content for {dest_repo.name}",
        code="import.repo.version.content",
        state=TASK_STATES.RUNNING,
    )
    pb.save()

    with tempfile.TemporaryDirectory() as temp_dir:
        # Extract the repo file for the repo info
        with tarfile.open(tar_path, "r:gz") as tar:
            tar.extract(REPO_FILE, path=temp_dir)

        with open(os.path.join(temp_dir, REPO_FILE), "r") as repo_data_file:
            data = json.load(repo_data_file)

        src_repo = next(repo for repo in data if repo["name"] == source_repo_name)

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

        rv_name = ""
        # Extract the repo version files
        with tarfile.open(tar_path, "r:gz") as tar:
            for mem in tar.getmembers():
                match = re.search(fr"(^repository-{source_repo_name}_[0-9]+)/.+", mem.name)
                if match:
                    rv_name = match.group(1)
                    tar.extract(mem, path=temp_dir)

        if not rv_name:
            raise ValidationError(_("No RepositoryVersion found for {}").format(rv_name))

        rv_path = os.path.join(temp_dir, rv_name)
        # Content
        plugin_name = src_repo["pulp_type"].split(".")[0]
        cfg = get_plugin_config(plugin_name)

        resulting_content_ids = []
        for res_class in cfg.exportable_classes:
            filename = f"{res_class.__module__}.{res_class.__name__}.json"
            a_result = _import_file(os.path.join(rv_path, filename), res_class, do_raise=False)
            # django import-export can have a problem with concurrent-imports that are
            # importing the same 'thing' (e.g., a Package that exists in two different
            # repo-versions that are being imported at the same time). We will try an import
            # that will simply record errors as they happen (rather than failing with an exception)
            # first. If errors happen, we'll do one retry before we give up on this repo-version's
            # import.
            if a_result.has_errors():
                log.info(
                    _("...{} import-errors encountered importing {} from {}, retrying").format(
                        a_result.totals["error"], filename, rv_name
                    )
                )
                # Second attempt, we allow to raise an exception on any problem.
                # This will either succeed, or log a fatal error and fail.
                try:
                    a_result = _import_file(os.path.join(rv_path, filename), res_class)
                except Exception as e:  # noqa log on ANY exception and then re-raise
                    log.error(
                        _("FATAL import-failure importing {} from {}").format(filename, rv_name)
                    )
                    raise

            resulting_content_ids.extend(
                row.object_id for row in a_result.rows if row.import_type in ("new", "update")
            )

        # Once all content exists, create the ContentArtifact links
        ca_path = os.path.join(rv_path, CA_FILE)
        _import_file(ca_path, ContentArtifactResource)

        # see if we have a content mapping
        mapping_path = f"{rv_name}/{CONTENT_MAPPING_FILE}"
        mapping = {}
        with tarfile.open(tar_path, "r:gz") as tar:
            if mapping_path in tar.getnames():
                tar.extract(mapping_path, path=temp_dir)
                with open(os.path.join(temp_dir, mapping_path), "r") as mapping_file:
                    mapping = json.load(mapping_file)

        if mapping:
            # use the content mapping to map content to repos
            for repo_name, content_ids in mapping.items():
                repo = _destination_repo(importer, repo_name)
                content = Content.objects.filter(upstream_id__in=content_ids)
                with repo.new_version() as new_version:
                    new_version.set_content(content)
        else:
            # just map all the content to our destination repo
            content = Content.objects.filter(pk__in=resulting_content_ids)
            with dest_repo.new_version() as new_version:
                new_version.set_content(content)

        content_count = content.count()
        pb.total = content_count
        pb.done = content_count
        pb.state = TASK_STATES.COMPLETED
        pb.save()

    gpr = TaskGroup.current().group_progress_reports.filter(code="import.repo.versions")
    gpr.update(done=F("done") + 1)


def pulp_import(importer_pk, path, toc):
    """
    Import a Pulp export into Pulp.

    Args:
        importer_pk (str): Primary key of PulpImporter to do the import
        path (str): Path to the export to be imported
    """

    def _compute_hash(filename):
        sha256_hash = hashlib.sha256()
        with open(filename, "rb") as f:
            # Read and update hash string value in blocks of 4K
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
            return sha256_hash.hexdigest()

    def validate_toc(toc_filename):
        """
        Check validity of table-of-contents file.

        table-of-contents must:
          * exist
          * be valid JSON
          * point to chunked-export-files that exist 'next to' the 'toc' file
          * point to chunks whose checksums match the checksums stored in the 'toc' file

        Args:
            toc_filename (str): The user-provided toc-file-path to be validated.

        Raises:
            ValidationError: If toc is not a valid JSON table-of-contents file,
            or when toc points to chunked-export-files that can't be found in the same
            directory as the toc-file, or the checksums of the chunks do not match the
            checksums stored in toc.
        """
        with open(toc_filename) as json_file:
            # Valid JSON?
            the_toc = json.load(json_file)
            if not the_toc.get("files", None) or not the_toc.get("meta", None):
                raise ValidationError(_("Missing 'files' or 'meta' keys in table-of-contents!"))

            base_dir = os.path.dirname(toc_filename)
            # Points at chunks that exist?
            missing_files = []
            for f in sorted(the_toc["files"].keys()):
                if not os.path.isfile(os.path.join(base_dir, f)):
                    missing_files.append(f)
            if missing_files:
                raise ValidationError(
                    _(
                        "Missing import-chunks named in table-of-contents: {}.".format(
                            str(missing_files)
                        )
                    )
                )

            errs = []
            # validate the sha256 of the toc-entries
            # gather errors for reporting at the end
            chunks = sorted(the_toc["files"].keys())
            data = dict(message="Validating Chunks", code="validate.chunks", total=len(chunks))
            with ProgressReport(**data) as pb:
                for chunk in pb.iter(chunks):
                    a_hash = _compute_hash(os.path.join(base_dir, chunk))
                    if not a_hash == the_toc["files"][chunk]:
                        err_str = "File {} expected checksum : {}, computed checksum : {}".format(
                            chunk, the_toc["files"][chunk], a_hash
                        )
                        errs.append(err_str)

            # if there are any errors, report and fail
            if errs:
                raise ValidationError(_("Import chunk hash mismatch: {}).").format(str(errs)))

        return the_toc

    def validate_and_assemble(toc_filename):
        """Validate checksums of, and reassemble, chunks in table-of-contents file."""
        the_toc = validate_toc(toc_filename)
        toc_dir = os.path.dirname(toc_filename)
        result_file = os.path.join(toc_dir, the_toc["meta"]["file"])

        # if we have only one entry in "files", it must be the full .tar.gz - return it
        if len(the_toc["files"]) == 1:
            return os.path.join(toc_dir, list(the_toc["files"].keys())[0])

        # We have multiple chunks.
        # reassemble into one file 'next to' the toc and return the resulting full-path
        chunk_size = int(the_toc["meta"]["chunk_size"])
        offset = 0
        block_size = 1024
        blocks_per_chunk = int(chunk_size / block_size)

        # sorting-by-filename is REALLY IMPORTANT here
        # keys are of the form <base-export-name>.00..<base-export-name>.NN,
        # and must be reassembled IN ORDER
        the_chunk_files = sorted(the_toc["files"].keys())

        data = dict(
            message="Recombining Chunks", code="recombine.chunks", total=len(the_chunk_files)
        )
        with ProgressReport(**data) as pb:
            for chunk in pb.iter(the_chunk_files):
                # For each chunk, add it to the reconstituted tar.gz, picking up where the previous
                # chunk left off
                subprocess.run(
                    [
                        "dd",
                        "if={}".format(os.path.join(toc_dir, chunk)),
                        "of={}".format(result_file),
                        "bs={}".format(str(block_size)),
                        "seek={}".format(str(offset)),
                    ],
                )
                offset += blocks_per_chunk
                # To keep from taking up All The Disk, we delete each chunk after it has been added
                # to the recombined file.
                try:
                    subprocess.run(["rm", "-f", os.path.join(toc_dir, chunk)])
                except OSError:
                    log.warning(
                        _("Failed to remove chunk {} after recombining. Continuing.").format(
                            os.path.join(toc_dir, chunk)
                        ),
                        exc_info=True,
                    )

        combined_hash = _compute_hash(result_file)
        if combined_hash != the_toc["meta"]["global_hash"]:
            raise ValidationError(
                _("Mismatch between combined .tar.gz checksum [{}] and originating [{}]).").format(
                    combined_hash, the_toc["meta"]["global_hash"]
                )
            )
        # if we get this far, then: the chunk-files all existed, they all pass checksum validation,
        # and there exists a combined .tar.gz, which *also* passes checksum-validation.
        # Let the rest of the import process do its thing on the new combined-file.
        return result_file

    if toc:
        log.info(_("Validating TOC {}.").format(toc))
        path = validate_and_assemble(toc)

    log.info(_("Importing {}.").format(path))
    current_task = Task.current()
    importer = PulpImporter.objects.get(pk=importer_pk)
    the_import = PulpImport.objects.create(
        importer=importer, task=current_task, params={"path": path}
    )
    CreatedResource.objects.create(content_object=the_import)

    task_group = TaskGroup.objects.create(description=f"Import of {path}")
    Task.objects.filter(pk=current_task.pk).update(task_group=task_group)
    current_task.refresh_from_db()
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
        data = dict(
            message="Importing Artifacts", code="import.artifacts", total=len(ar_result.rows)
        )
        with ProgressReport(**data) as pb:
            for row in pb.iter(ar_result.rows):
                artifact = Artifact.objects.get(pk=row.object_id)
                base_path = os.path.join("artifact", artifact.sha256[0:2], artifact.sha256[2:])
                src = os.path.join(temp_dir, base_path)
                dest = os.path.join(settings.MEDIA_ROOT, base_path)

                if not default_storage.exists(dest):
                    with open(src, "rb") as f:
                        default_storage.save(dest, f)

        with open(os.path.join(temp_dir, REPO_FILE), "r") as repo_data_file:
            data = json.load(repo_data_file)
            gpr = GroupProgressReport(
                message="Importing repository versions",
                code="import.repo.versions",
                total=len(data),
                done=0,
                task_group=task_group,
            )
            gpr.save()

            for src_repo in data:
                try:
                    dest_repo = _destination_repo(importer, src_repo["name"])
                except Repository.DoesNotExist:
                    log.warning(
                        _("Could not find destination repo for {}. Skipping.").format(
                            src_repo["name"]
                        )
                    )
                    continue

                dispatch(
                    import_repository_version,
                    [dest_repo],
                    args=[importer.pk, dest_repo.pk, src_repo["name"], path],
                    task_group=task_group,
                )

    task_group.finish()
