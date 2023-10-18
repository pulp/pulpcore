import logging
import tempfile

from gettext import gettext as _

from django.core.files import File

from pulpcore.plugin.models import (
    ContentArtifact,
    RepositoryVersion,
    PublishedMetadata,
    RemoteArtifact,
)

from pulp_file.app.models import FilePublication
from pulp_file.manifest import Entry, Manifest


log = logging.getLogger(__name__)


def publish(manifest, repository_version_pk):
    """
    Create a Publication based on a RepositoryVersion.

    Args:
        manifest (str): Filename to use for manifest file.
        repository_version_pk (str): Create a publication from this repository version.

    """
    repo_version = RepositoryVersion.objects.get(pk=repository_version_pk)

    log.info(
        _("Publishing: repository={repo}, version={ver}, manifest={manifest}").format(
            repo=repo_version.repository.name, ver=repo_version.number, manifest=manifest
        )
    )

    with tempfile.TemporaryDirectory(dir="."):
        with FilePublication.create(repo_version, pass_through=True) as publication:
            publication.manifest = manifest
            if manifest:
                manifest = Manifest(manifest)
                manifest.write(yield_entries_for_version(repo_version))
                PublishedMetadata.create_from_file(
                    file=File(open(manifest.relative_path, "rb")), publication=publication
                )

        log.info(_("Publication: {publication} created").format(publication=publication.pk))

        return publication


def yield_entries_for_version(repo_version):
    """
    Yield a Manifest Entry for every content in the repository version.

    Args:
        repo_version (pulpcore.plugin.models.RepositoryVersion):
            A RepositoryVersion to manifest entries for.

    Yields:
        Entry: Each manifest entry.

    """

    content_artifacts = ContentArtifact.objects.filter(content__in=repo_version.content).order_by(
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
