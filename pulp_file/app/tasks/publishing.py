import logging
import tempfile
from gettext import gettext as _

from django.core.files import File

from pulpcore.plugin.models import (
    ContentArtifact,
    PublishedMetadata,
    RemoteArtifact,
    Repository,
    RepositoryVersion,
)

from pulp_file.app.models import FilePublication, FileRepository
from pulp_file.app.serializers import FilePublicationSerializer
from pulp_file.manifest import Entry, Manifest, Sha256Sums

log = logging.getLogger(__name__)


def publish(
    manifest,
    repository_version_pk=None,
    repository_pk=None,
    sha256sums=FileRepository.SHA256SUMS_DISABLED,
    checkpoint=False,
    **kwargs,
):
    """
    Create a Publication based on a RepositoryVersion.

    Args:
        manifest (str): Filename to use for manifest file.
        repository_version_pk (str): Create a publication from this repository version.
        repository_pk (str): Create a publication from this unversioned repository, with its
            content at its current change sequence number. Set instead of repository_version_pk.
        sha256sums (str): Whether to generate SHA256SUMS files, and where to place them.
        checkpoint (bool): Whether to create a checkpoint publication.

    """
    if repository_pk:
        repo_version = Repository.objects.get(pk=repository_pk).cast().latest_version()
    else:
        repo_version = RepositoryVersion.objects.get(pk=repository_version_pk)

    log.info(
        _(
            "Publishing: repository={repo}, version={ver}, manifest={manifest}, "
            "sha256sums={sha256sums}"
        ).format(
            repo=repo_version.repository.name,
            ver=repo_version.number if repository_version_pk else "unversioned",
            manifest=manifest,
            sha256sums=sha256sums,
        )
    )

    with tempfile.TemporaryDirectory(dir=".") as temp_dir:
        with FilePublication.create(
            repo_version, pass_through=True, checkpoint=checkpoint
        ) as publication:
            # For an unversioned repository, the content at the stored seq
            content = publication.published_version.content
            publication.manifest = manifest
            publication.sha256sums = sha256sums
            if manifest:
                entries = _patched_manifest_entries(publication, manifest)
                if entries is None:
                    entries = yield_entries_for_content(content)
                manifest = Manifest(manifest)
                manifest.write(entries)
                PublishedMetadata.create_from_file(
                    file=File(open(manifest.relative_path, "rb")), publication=publication
                )
            # Unlike the manifest, these are always built from all content
            if sha256sums != FileRepository.SHA256SUMS_DISABLED:
                sums = Sha256Sums(per_directory=sha256sums == FileRepository.SHA256SUMS_DIRECTORY)
                written = sums.write(yield_entries_for_content(content), temp_dir)
                for relative_path, local_path in written.items():
                    PublishedMetadata.create_from_file(
                        file=File(open(local_path, "rb")),
                        relative_path=relative_path,
                        publication=publication,
                    )

        log.info(_("Publication: {publication} created").format(publication=publication.pk))

        publication = FilePublicationSerializer(
            instance=publication, context={"request": None}
        ).data

        return publication


def yield_entries_for_content(content):
    """
    Yield a Manifest Entry for every content artifact of the content.

    Args:
        content (django.db.models.QuerySet): The content to manifest entries for.

    Yields:
        Entry: Each manifest entry.

    """
    content_artifacts = ContentArtifact.objects.filter(content__in=content).order_by(
        "-content__pulp_created"
    )

    for content_artifact in content_artifacts.select_related("artifact").iterator():
        if content_artifact.artifact:
            artifact = content_artifact.artifact
        else:
            # TODO: this scales poorly, one query per on_demand content being published.
            artifact = RemoteArtifact.objects.filter(content_artifact=content_artifact).first()
        entry = Entry(
            relative_path=content_artifact.relative_path,
            digest=artifact.sha256,
            size=artifact.size,
        )
        yield entry


def _patched_manifest_entries(publication, manifest):
    """
    Return manifest entries made by patching the manifest of the previous publication.

    Only the content changed since the previous publication is read from the database, so this
    scales with the number of changes. The previous manifest file is still read in full.

    Args:
        publication (pulp_file.app.models.FilePublication): The publication being created.
        manifest (str): Filename of the manifest.

    Returns:
        A generator of Entry, or None if there is no previous publication of the unversioned
        repository to patch.
    """
    if not publication.unversioned_repository_id:
        return None
    previous = (
        FilePublication.objects.filter(
            unversioned_repository=publication.unversioned_repository,
            seq__lte=publication.seq,
            manifest=manifest,
            complete=True,
        )
        .order_by("-seq", "-pulp_created")
        .first()
    )
    if previous is None:
        return None
    metadata = previous.published_metadata.get(relative_path=manifest)
    with metadata.contentartifact_set.get().artifact.file.open() as fp:
        previous_manifest = fp.read().decode()
    log.info(
        _("Patching the manifest of publication {pk} at seq {seq}").format(
            pk=previous.pk, seq=previous.seq
        )
    )

    added, removed = publication.published_version.changes_since(previous.seq)
    removed_paths = set(
        ContentArtifact.objects.filter(content__in=removed).values_list("relative_path", flat=True)
    )

    def entries():
        for entry in Manifest.parse(previous_manifest):
            if entry.relative_path not in removed_paths:
                yield entry
        yield from yield_entries_for_content(added)

    return entries()
