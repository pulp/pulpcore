import logging
import os

from gettext import gettext as _
from urllib.parse import urlparse, urlunparse

from django.core.files import File

from pulpcore.plugin.models import Artifact, ProgressReport, Remote, PublishedMetadata
from pulpcore.plugin.stages import (
    DeclarativeArtifact,
    DeclarativeContent,
    DeclarativeVersion,
    Stage,
)

from pulp_file.app.models import FileContent, FileRemote, FileRepository, FilePublication
from pulp_file.manifest import Manifest


log = logging.getLogger(__name__)


metadata_files = []


def synchronize(remote_pk, repository_pk, mirror, url=None):
    """
    Sync content from the remote repository.

    Create a new version of the repository that is synchronized with the remote.

    Args:
        remote_pk (str): The remote PK.
        repository_pk (str): The repository PK.
        mirror (bool): True for mirror mode, False for additive.
        url (str): The url to synchronize. If omitted, the url of the remote is used.

    Raises:
        ValueError: If the remote does not specify a URL to sync.

    """
    remote = FileRemote.objects.get(pk=remote_pk)
    repository = FileRepository.objects.get(pk=repository_pk)

    if not remote.url:
        raise ValueError(_("A remote must have a url specified to synchronize."))

    first_stage = FileFirstStage(remote, url)
    dv = DeclarativeVersion(first_stage, repository, mirror=mirror, acs=True)
    rv = dv.create()
    if rv and mirror:
        # TODO: this is awful, we really should rewrite the DeclarativeVersion API to
        # accomodate this use case
        global metadata_files
        with FilePublication.create(rv, pass_through=True) as publication:
            (mdfile_path, relative_path) = metadata_files.pop()
            PublishedMetadata.create_from_file(
                file=File(open(mdfile_path, "rb")),
                relative_path=relative_path,
                publication=publication,
            )
            publication.manifest = relative_path
            publication.save()

        log.info(_("Publication: {publication} created").format(publication=publication.pk))

    return rv


class FileFirstStage(Stage):
    """
    The first stage of a pulp_file sync pipeline.
    """

    def __init__(self, remote, url):
        """
        The first stage of a pulp_file sync pipeline.

        Args:
            remote (FileRemote): The remote data to be used when syncing
            url (str): The base url of custom remote

        """
        super().__init__()
        self.remote = remote
        self.url = url if url else remote.url

    async def run(self):
        """
        Build and emit `DeclarativeContent` from the Manifest data.
        """
        global metadata_files

        deferred_download = self.remote.policy != Remote.IMMEDIATE  # Interpret download policy
        async with ProgressReport(
            message="Downloading Metadata", code="sync.downloading.metadata"
        ) as pb:
            parsed_url = urlparse(self.url)
            root_dir = os.path.dirname(parsed_url.path)
            downloader = self.remote.get_downloader(url=self.url)
            result = await downloader.run()
            await pb.aincrement()
            metadata_files.append((result.path, self.url.split("/")[-1]))

        async with ProgressReport(
            message="Parsing Metadata Lines", code="sync.parsing.metadata"
        ) as pb:
            manifest = Manifest(result.path)
            entries = list(manifest.read())

            pb.total = len(entries)
            await pb.asave()

            for entry in entries:
                path = os.path.join(root_dir, entry.relative_path)
                url = urlunparse(parsed_url._replace(path=path))
                file = FileContent(relative_path=entry.relative_path, digest=entry.digest)
                artifact = Artifact(size=entry.size, sha256=entry.digest)
                da = DeclarativeArtifact(
                    artifact=artifact,
                    url=url,
                    relative_path=entry.relative_path,
                    remote=self.remote,
                    deferred_download=deferred_download,
                )
                dc = DeclarativeContent(content=file, d_artifacts=[da])
                await pb.aincrement()
                await self.put(dc)
