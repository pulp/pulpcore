import json
import os
import re
import tempfile
import tarfile
from contextlib import ExitStack, nullcontext
from gettext import gettext as _
from logging import getLogger

import json_stream
from django.conf import settings
from django.core.files.storage import default_storage
from django.db.models import F
from io import StringIO
from rest_framework.serializers import ValidationError
from tablib import Dataset

from pulpcore.exceptions.plugin import MissingPlugin
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
    Worker,
)
from pulpcore.app.modelresource import (
    ArtifactResource,
    ContentArtifactResource,
    RepositoryResource,
)
from pulpcore.app.util import compute_file_hash, Crc32Hasher
from pulpcore.constants import TASK_STATES
from pulpcore.tasking.tasks import dispatch

from pulpcore.plugin.importexport import BaseContentResource

log = getLogger(__name__)

ARTIFACT_FILE = "pulpcore.app.modelresource.ArtifactResource.json"
REPO_FILE = "pulpcore.app.modelresource.RepositoryResource.json"
CONTENT_FILE = "pulpcore.app.modelresource.ContentResource.json"
CA_FILE = "pulpcore.app.modelresource.ContentArtifactResource.json"
VERSIONS_FILE = "versions.json"
CONTENT_MAPPING_FILE = "content_mapping.json"
# How many entities from an import-file should be processed at one time
IMPORT_BATCH_SIZE = 100

# Concurrent imports w/ overlapping content can collide - how many attempts are we willing to
# make before we decide this is a fatal error?
MAX_ATTEMPTS = 3


class ChunkedFile(ExitStack):
    """
    Read a toc file and represent the reconstructed file as a fileobj.

    This class implements just enough of the fileobj interface to let `tarfile` work on a bunch of
    file chunks.

    `validate_chunks` can be called after `__init__` to verify the existance and checksums of the
    chunks. All other operations need to be done using this object as a context manager.
    """

    def __init__(self, toc_path):
        super().__init__()
        with open(toc_path, "r") as toc_file:
            self.toc = json.load(toc_file)
        if "files" not in self.toc or "meta" not in self.toc:
            raise ValidationError(_("Missing 'files' or 'meta' keys in table-of-contents!"))

        toc_dir = os.path.dirname(toc_path)
        # sorting-by-filename is REALLY IMPORTANT here
        # keys are of the form <base-export-name>.00..<base-export-name>.NN,
        # and must be reassembled IN ORDER
        self.chunk_names = sorted(self.toc["files"].keys())
        self.chunk_paths = [os.path.join(toc_dir, chunk_name) for chunk_name in self.chunk_names]
        self.chunk_size = int(self.toc["meta"].get("chunk_size", 0))
        if not self.chunk_size:
            assert (
                len(self.toc["files"]) == 1
            ), "chunk_size must exist and be non-zero if more than one chunk exists"
            self.chunk_size = os.path.getsize(self.chunk_paths[0])

    def __enter__(self):
        assert not hasattr(self, "chunks"), "ChunkedFile is not reentrant."
        super().__enter__()
        self.chunks = [
            self.enter_context(open(chunk_path, "rb")) for chunk_path in self.chunk_paths
        ]
        self.chunk = 0
        self.offset = 0
        return self

    def __exit__(self, *exc):
        super().__exit__(*exc)
        del self.chunks
        del self.chunk
        del self.offset

    def tell(self):
        return self.chunk_size * self.chunk + self.offset

    def read(self, size):
        data = b""  # Accumulator
        remaining_size = size
        while True:
            assert remaining_size > 0
            current_size = min(self.chunk_size - self.offset, remaining_size)
            piece = self.chunks[self.chunk].read(current_size)
            read_size = len(piece)
            data += piece
            self.offset += read_size
            remaining_size -= read_size
            if read_size < current_size:
                # Reached EOF (should only happen on the last chunk)
                if self.chunk != len(self.chunks) - 1:
                    raise Exception(f"Short read from chunk {self.chunk}.")
                return data
            if remaining_size == 0:
                return data
            if self.chunk == len(self.chunks) - 1:
                return data
            assert self.offset == self.chunk_size
            self.chunk += 1
            self.offset = 0
            self.chunks[self.chunk].seek(0)

    def seek(self, target, whence=0):
        assert whence == 0  # not implemented... (also not needed either)
        self.chunk = target // self.chunk_size
        self.offset = target % self.chunk_size
        self.chunks[self.chunk].seek(self.offset)

    def validate_chunks(self):
        """
        Check validity of table-of-contents file.

        table-of-contents must:
          * exist
          * be valid JSON
          * point to chunked-export-files that exist 'next to' the 'toc' file
          * point to chunks whose checksums match the checksums stored in the 'toc' file

        Raises:
            ValidationError: When toc points to chunked-export-files that can't be found in the
            same directory as the toc-file, or the checksums of the chunks do not match the
            checksums stored in toc.
        """
        # Check all chunks exist
        missing_files = []
        for chunk_path in self.chunk_paths:
            if not os.path.isfile(chunk_path):
                missing_files.append(chunk_path)
        if missing_files:
            raise ValidationError(
                _(
                    "Missing import-chunks named in table-of-contents: {}.".format(
                        str(missing_files)
                    )
                )
            )

        errs = []
        # validate the digests of the toc-entries
        # gather errors for reporting at the end
        data = dict(
            message="Validating Chunks", code="validate.chunks", total=len(self.chunk_paths)
        )
        with ProgressReport(**data) as pb:
            for chunk_name, chunk_path in pb.iter(zip(self.chunk_names, self.chunk_paths)):
                expected_hash = self.toc["files"][chunk_name]
                chunk_hash = compute_file_hash(chunk_path, hasher=Crc32Hasher())
                if chunk_hash != expected_hash:
                    err_str = "File {} expected checksum : {}, computed checksum : {}".format(
                        chunk_name, expected_hash, chunk_hash
                    )
                    errs.append(err_str)

        # if there are any errors, report and fail
        if errs:
            raise ValidationError(_("Import chunk hash mismatch: {}).").format(str(errs)))


def _get_destination_repo_name(importer, source_repo_name):
    """
    Return the name of a destination repository considering the mapping or source repository name.
    """
    if importer.repo_mapping and importer.repo_mapping.get(source_repo_name):
        dest_repo_name = importer.repo_mapping[source_repo_name]
    else:
        dest_repo_name = source_repo_name
    return dest_repo_name


def _impfile_iterator(fd):
    """
    Iterate over an import-file returning batches of rows as a json-array-string.

    We use naya.json.stream_array() to get individual rows; once a batch is gathered,
    we yield the result of json.dumps() for that batch. Repeat until all rows have been
    called for.
    """
    data = json_stream.load(fd)
    batch = []
    for row in data:
        batch.append(json_stream.to_standard_types(row))
        if len(batch) >= IMPORT_BATCH_SIZE:
            yield json.dumps(batch)
            batch.clear()
    yield json.dumps(batch)


def _import_file(fpath, resource_class, retry=False):
    """
    Import the specified resource-file in batches to limit memory-use.

    We process resource-files one "batch" at a time. Because of the way django-import's
    internals work, we have to feed it batches as StringIO-streams of json-formatted strings.
    The file-to-json-to-string-to-import is overhead, but it lets us put an upper bound on the
    number of entities in memory at any one time at import-time.
    """
    try:
        log.info(f"Importing file {fpath}.")
        with open(fpath, "r") as json_file:
            resource = resource_class()
            log.info(f"...Importing resource {resource.__class__.__name__}.")
            # Load one batch-sized chunk of the specified import-file at a time. If requested,
            # retry a batch if it looks like we collided with some other repo being imported with
            # overlapping content.
            for batch_str in _impfile_iterator(json_file):
                data = Dataset().load(StringIO(batch_str))
                if retry:
                    curr_attempt = 1

                    while curr_attempt < MAX_ATTEMPTS:
                        curr_attempt += 1
                        # django import-export can have a problem with concurrent-imports that are
                        # importing the same 'thing' (e.g., a Package that exists in two different
                        # repo-versions that are being imported at the same time). If we're asked to
                        # retry, we will try an import that will simply record errors as they happen
                        # (rather than failing with an exception) first. If errors happen, we'll
                        # retry before we give up on this repo-version's import.
                        a_result = resource.import_data(data, raise_errors=False)
                        if a_result.has_errors():
                            total_errors = a_result.totals["error"]
                            log.info(
                                "...{total_errors} import-errors encountered importing {fpath}, "
                                "attempt {curr_attempt}, retrying".format(
                                    total_errors=total_errors,
                                    fpath=fpath,
                                    curr_attempt=curr_attempt,
                                )
                            )
                        else:
                            break
                    else:
                        # The while condition is not fulfilled, so we proceed to the last attempt,
                        # we raise an exception on any problem. This will either succeed, or log a
                        # fatal error and fail.
                        try:
                            a_result = resource.import_data(data, raise_errors=True)
                        except Exception as e:  # noqa log on ANY exception and then re-raise
                            log.error(f"FATAL import-failure importing {fpath}")
                            raise
                else:
                    a_result = resource.import_data(data, raise_errors=True)
                yield a_result
    except AttributeError:
        log.error(f"FAILURE loading import-file {fpath}!")
        raise


def _check_versions(version_json):
    """
    Compare the export version_json to the installed components.

    An upstream whose db-metadata doesn't match the downstream won't import successfully; check
    for compatibility and raise a ValidationError if incompatible versions are found.
    """
    error_messages = []
    for component in version_json:
        try:
            version = get_plugin_config(component["component"]).version
        except MissingPlugin:
            error_messages.append(
                _("Export uses {} which is not installed.").format(component["component"])
            )
        else:
            # Check that versions are compatible. Currently, "compatible" is defined as "same X.Y".
            # Versions are strings that generally look like "X.Y.Z" or "X.Y.Z.dev"; we check that
            # first two places are the same.
            if version.split(".")[:2] != component["version"].split(".")[:2]:
                error_messages.append(
                    _(
                        "Export version {export_ver} of {component} incompatible with "
                        "installed version {ver}."
                    ).format(
                        export_ver=component["version"],
                        component=component["component"],
                        ver=version,
                    )
                )

    if error_messages:
        raise ValidationError((" ".join(error_messages)))


def import_repository_version(
    importer_pk, src_repo_name, src_repo_type, dest_repo_name, dest_repo_pk, tar_path, toc_path=None
):
    """
    Import a repository version from a Pulp export.

    Args:
        importer_pk (str): Importer we are working with.
        src_repo_name (str): The name of the original repository.
        src_repo_type (str): The Pulp's type of a repository.
        dest_repo_name (str): The name of a repository where the content will be imported.
        dest_repo_pk (str): The primary key of a destination repository if any
        tar_path (str): The path of an exported tarball.
        toc_path (str): The path to the TableOfContents file for the import (if it was provided).
    """
    importer = PulpImporter.objects.get(pk=importer_pk)

    pb = ProgressReport(
        message=f"Importing content for {dest_repo_name}",
        code="import.repo.version.content",
        state=TASK_STATES.RUNNING,
    )
    pb.save()

    with tempfile.TemporaryDirectory(dir=".") as temp_dir:
        if toc_path:
            fileobj = ChunkedFile(toc_path)
        else:
            fileobj = nullcontext()
        # Extract the repo file for the repo info
        with fileobj as fp:
            with tarfile.open(tar_path, "r", fileobj=fp) as tar:
                tar.extract(REPO_FILE, path=temp_dir)

                rv_name = ""
                # Extract the repo version files
                for mem in tar.getmembers():
                    match = re.search(rf"(^repository-{src_repo_name}_[0-9]+)/.+", mem.name)
                    if match:
                        rv_name = match.group(1)
                        tar.extract(mem, path=temp_dir)

                if not rv_name:
                    raise ValidationError(_("No RepositoryVersion found for {}").format(rv_name))

                rv_path = os.path.join(temp_dir, rv_name)

                # see if we have a Content mapping
                mapping_path = f"{rv_name}/{CONTENT_MAPPING_FILE}"
                mapping = {}
                if mapping_path in tar.getnames():
                    tar.extract(mapping_path, path=temp_dir)
                    with open(os.path.join(temp_dir, mapping_path), "r") as mapping_file:
                        mapping = json.load(mapping_file)

        # Content
        app_label = src_repo_type.split(".")[0]
        cfg = get_plugin_config(app_label)

        resulting_content_ids = []
        for res_class in cfg.exportable_classes:
            if issubclass(res_class, RepositoryResource) and dest_repo_pk:
                continue

            filename = f"{res_class.__module__}.{res_class.__name__}.json"
            for a_result in _import_file(os.path.join(rv_path, filename), res_class, retry=True):
                if issubclass(res_class, RepositoryResource) and a_result.rows:
                    repo_resource = a_result.rows[0]
                    if repo_resource.import_type in ("new", "update"):
                        dest_repo_pk = repo_resource.object_id

                if not mapping and issubclass(res_class, BaseContentResource):
                    resulting_content_ids.extend(
                        row.object_id
                        for row in a_result.rows
                        if row.import_type in ("new", "update")
                    )

        # Once all content exists, create the ContentArtifact links
        ca_path = os.path.join(rv_path, CA_FILE)
        # We don't do anything with the imported batches, we just need to get them imported
        for a_batch in _import_file(ca_path, ContentArtifactResource, retry=True):
            pass

        content_count = 0
        if mapping:
            # use the content mapping to map content to repos
            for repo_name, content_ids in mapping.items():
                repo_name = _get_destination_repo_name(importer, repo_name)
                dest_repo = Repository.objects.get(name=repo_name)
                content = Content.objects.filter(upstream_id__in=content_ids)
                content_count += len(content_ids)
                with dest_repo.new_version() as new_version:
                    new_version.set_content(content)
        else:
            # just map all the content to our destination repo
            dest_repo = Repository.objects.get(pk=dest_repo_pk)
            content = Content.objects.filter(pk__in=resulting_content_ids)
            content_count += len(resulting_content_ids)
            with dest_repo.new_version() as new_version:
                new_version.set_content(content)

        pb.total = content_count
        pb.done = content_count
        pb.state = TASK_STATES.COMPLETED
        pb.save()

    gpr = TaskGroup.current().group_progress_reports.filter(code="import.repo.versions")
    gpr.update(done=F("done") + 1)


def pulp_import(importer_pk, path, toc, create_repositories):
    """
    Import a Pulp export into Pulp.

    Args:
        importer_pk (str): Primary key of PulpImporter to do the import
        path (str): Path to the export to be imported
        toc (str): The path to a table-of-contents file describing chunks to be validated,
            reassembled, and imported.
        create_repositories (bool): Indicates whether missing repositories should be automatically
            created or not.
    """

    if toc:
        path = toc
        fileobj = ChunkedFile(toc)
        log.info(_("Validating TOC {}.").format(toc))
        fileobj.validate_chunks()
    else:
        fileobj = nullcontext()

    log.info(_("Importing {}.").format(path))
    current_task = Task.current()
    task_group = TaskGroup.current()
    importer = PulpImporter.objects.get(pk=importer_pk)
    the_import = PulpImport.objects.create(
        importer=importer, task=current_task, params={"path": path}
    )
    CreatedResource.objects.create(content_object=the_import)

    with tempfile.TemporaryDirectory(dir=".") as temp_dir:
        with fileobj as fp:
            with tarfile.open(path, "r", fileobj=fp) as tar:

                def is_within_directory(directory, target):
                    abs_directory = os.path.abspath(directory)
                    abs_target = os.path.abspath(target)

                    prefix = os.path.commonprefix([abs_directory, abs_target])

                    return prefix == abs_directory

                def safe_extract(tar, path=".", members=None, *, numeric_owner=False):
                    for member in tar.getmembers():
                        member_path = os.path.join(path, member.name)
                        if not is_within_directory(path, member_path):
                            raise Exception("Attempted Path Traversal in Tar File")

                    tar.extractall(path, members, numeric_owner=numeric_owner)

                safe_extract(tar, path=temp_dir)

        # Check version info
        with open(os.path.join(temp_dir, VERSIONS_FILE)) as version_file:
            version_json = json.load(version_file)
            _check_versions(version_json)

        # Artifacts
        data = dict(
            message="Importing Artifacts",
            code="import.artifacts",
        )
        with ProgressReport(**data) as pb:
            # Import artifacts, and place their binary blobs, one batch at a time.
            # Skip artifacts that already exist in storage.
            for ar_result in _import_file(os.path.join(temp_dir, ARTIFACT_FILE), ArtifactResource):
                for row in pb.iter(ar_result.rows):
                    artifact = Artifact.objects.get(pk=row.object_id)
                    base_path = os.path.join("artifact", artifact.sha256[0:2], artifact.sha256[2:])
                    src = os.path.join(temp_dir, base_path)

                    if not default_storage.exists(base_path):
                        with open(src, "rb") as f:
                            default_storage.save(base_path, f)

        # Now import repositories, in parallel.

        # We want to be able to limit the number of available-workers that import will consume,
        # so that pulp can continue to work while doing an import. We accomplish this by creating
        # a reserved-resource string for each repo-import-task based on that repo's index in
        # the dispatch loop, mod number-of-workers-to-consume.
        #
        # By default (setting is not-set), import will continue to use 100% of the available
        # workers.
        import_workers_percent = int(settings.get("IMPORT_WORKERS_PERCENT", 100))
        total_workers = Worker.objects.online().count()
        import_workers = max(1, int(total_workers * (import_workers_percent / 100.0)))

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

            for index, src_repo in enumerate(data):
                # Lock the repo we're importing-into
                dest_repo_name = _get_destination_repo_name(importer, src_repo["name"])
                # pulpcore-worker limiter
                worker_rsrc = f"import-worker-{index % import_workers}"
                exclusive_resources = [worker_rsrc]
                try:
                    dest_repo = Repository.objects.get(name=dest_repo_name)
                except Repository.DoesNotExist:
                    if create_repositories:
                        dest_repo_pk = ""
                    else:
                        log.warning(
                            "Could not find destination repo for {}. Skipping.".format(
                                src_repo["name"]
                            )
                        )
                        continue
                else:
                    exclusive_resources.append(dest_repo)
                    dest_repo_pk = dest_repo.pk

                dispatch(
                    import_repository_version,
                    exclusive_resources=exclusive_resources,
                    args=(
                        importer.pk,
                        src_repo["name"],
                        src_repo["pulp_type"],
                        dest_repo_name,
                        dest_repo_pk,
                        path,
                        toc,
                    ),
                    task_group=task_group,
                )

    task_group.finish()
