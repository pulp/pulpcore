import logging
import os
import re
import shutil
import tempfile

from gettext import gettext as _
from urllib.parse import quote, urlparse, urlunparse

import git as gitpython
from gitdb.exc import BadName, BadObject
from django.core.files import File

from pulpcore.plugin.exceptions import SyncError
from pulpcore.plugin.models import Artifact, ProgressReport, Remote, PublishedMetadata
from pulpcore.plugin.serializers import RepositoryVersionSerializer
from pulpcore.plugin.stages import (
    DeclarativeArtifact,
    DeclarativeContent,
    DeclarativeVersion,
    RemoteArtifactSaver,
    Stage,
)

from pulp_file.app.models import (
    FileContent,
    FileGitRemote,
    FileRepository,
    FilePublication,
)
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
    remote = Remote.objects.get(pk=remote_pk).cast()
    repository = FileRepository.objects.get(pk=repository_pk)

    if not remote.url:
        raise ValueError(_("A remote must have a url specified to synchronize."))

    if isinstance(remote, FileGitRemote):
        first_stage = GitFirstStage(remote)
        dv = DeclarativeVersion(first_stage, repository, mirror=mirror)
        old_pipeline_stages = dv.pipeline_stages
        dv.pipeline_stages = lambda new_version: [
            stage
            for stage in old_pipeline_stages(new_version)
            if not isinstance(stage, (RemoteArtifactSaver))
        ]
    else:
        first_stage = FileFirstStage(remote, url)
        dv = DeclarativeVersion(first_stage, repository, mirror=mirror, acs=True)
    rv = dv.create()
    if rv and mirror:
        # TODO: this is awful, we really should rewrite the DeclarativeVersion API to
        # accomodate this use case
        global metadata_files
        with FilePublication.create(rv, pass_through=True) as publication:
            mdfile_path, relative_path = metadata_files.pop()
            PublishedMetadata.create_from_file(
                file=File(open(mdfile_path, "rb")),
                relative_path=relative_path,
                publication=publication,
            )
            publication.manifest = relative_path
            publication.save()

        log.info(_("Publication: {publication} created").format(publication=publication.pk))

    if rv:
        rv = RepositoryVersionSerializer(instance=rv, context={"request": None}).data

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
                path = _get_safe_path(root_dir, entry, parsed_url.scheme)

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


def _get_safe_path(root_dir, entry, scheme):
    relative_path = entry.relative_path.lstrip("/")
    path = os.path.join(root_dir, relative_path)
    return path if scheme == "file" else quote(path, safe=":/")


def _build_clone_env(remote):
    """
    Build environment variables for git clone that apply the remote's auth and proxy settings.

    Args:
        remote (FileGitRemote): The remote with auth/proxy/TLS configuration.

    Returns:
        dict: Environment variables to pass to git commands.
    """
    env = os.environ.copy()

    # Proxy configuration
    if remote.proxy_url:
        proxy_url = remote.proxy_url
        if remote.proxy_username and remote.proxy_password:
            parsed = urlparse(proxy_url)
            proxy_url = urlunparse(
                parsed._replace(
                    netloc=f"{remote.proxy_username}:{remote.proxy_password}@{parsed.hostname}"
                    + (f":{parsed.port}" if parsed.port else "")
                )
            )
        env["http_proxy"] = proxy_url
        env["https_proxy"] = proxy_url

    # TLS validation
    if not remote.tls_validation:
        env["GIT_SSL_NO_VERIFY"] = "true"

    # CA certificate
    if remote.ca_cert:
        ca_cert_file = tempfile.NamedTemporaryFile(dir=".", suffix=".pem", delete=False, mode="w")
        ca_cert_file.write(remote.ca_cert)
        ca_cert_file.close()
        env["GIT_SSL_CAINFO"] = ca_cert_file.name

    # Client certificate and key
    if remote.client_cert:
        client_cert_file = tempfile.NamedTemporaryFile(
            dir=".", suffix=".pem", delete=False, mode="w"
        )
        client_cert_file.write(remote.client_cert)
        client_cert_file.close()
        env["GIT_SSL_CERT"] = client_cert_file.name

    if remote.client_key:
        client_key_file = tempfile.NamedTemporaryFile(
            dir=".", suffix=".key", delete=False, mode="w"
        )
        client_key_file.write(remote.client_key)
        client_key_file.close()
        env["GIT_SSL_KEY"] = client_key_file.name

    return env


def _build_clone_url(remote):
    """
    Build the clone URL, embedding basic auth credentials if present on the remote.

    Args:
        remote (FileGitRemote): The remote with URL and optional credentials.

    Returns:
        str: The URL to use for git clone.
    """
    url = remote.url
    if remote.username and remote.password:
        parsed = urlparse(url)
        if parsed.scheme in ("http", "https"):
            url = urlunparse(
                parsed._replace(
                    netloc=f"{remote.username}:{remote.password}@{parsed.hostname}"
                    + (f":{parsed.port}" if parsed.port else "")
                )
            )
    return url


_LFS_POINTER_RE = re.compile(
    rb"^version https://git-lfs\.github\.com/spec/v1\n"
    rb"oid sha256:([0-9a-f]{64})\n"
    rb"size (\d+)\n$"
)


class GitFirstStage(Stage):
    """
    The first stage of a pulp_file sync pipeline for Git repositories.

    Performs a bare clone of the Git repository, resolves the specified git_ref, and
    walks the tree to emit ``DeclarativeContent`` for each blob. Computes sha256 for
    each blob so that ``QueryExistingArtifacts`` can match already-known artifacts and
    ``FileContent.digest`` is available for content matching.
    """

    def __init__(self, remote):
        """
        Args:
            remote (FileGitRemote): The git remote data to be used when syncing.
        """
        super().__init__()
        self.remote = remote

    def _parse_lfs_pointer(self, data):
        """Returns the oid and size of an LFS pointer if present."""
        match = _LFS_POINTER_RE.match(data)
        if match:
            return match.group(1).decode(), int(match.group(2))
        return None

    def _build_lfs_api_url(self):
        """Derive the LFS API endpoint from the git remote URL."""
        url = self.remote.url.rstrip("/")
        if not url.endswith(".git"):
            url += ".git"
        return f"{url}/info/lfs/objects/batch"

    async def _fetch_lfs_batch(self, lfs_blobs):
        """Resolves the LFS pointers to downloadable links."""
        lfs_api_url = self._build_lfs_api_url()
        headers = {
            "Content-Type": "application/vnd.git-lfs+json",
            "Accept": "application/vnd.git-lfs+json",
        }
        data = {
            "operation": "download",
            "transfer": "basic",
            "objects": [{"oid": oid, "size": size} for rp, oid, size in lfs_blobs],
        }
        downloader = self.remote.get_downloader(url=lfs_api_url)
        session = downloader.session
        async with session.post(lfs_api_url, headers=headers, json=data) as response:
            response.raise_for_status()
            return await response.json()

    async def run(self):
        """
        Build and emit `DeclarativeContent` from the Git repository tree.
        """

        remote = self.remote
        git_ref = remote.git_ref or "HEAD"
        clone_url = _build_clone_url(remote)
        clone_env = _build_clone_env(remote)

        clone_dir = tempfile.mkdtemp(dir=".", prefix="pulp_file_git_")

        async with ProgressReport(message="Cloning Git Repository", code="sync.git.cloning") as pb:
            try:
                try:
                    repo = gitpython.Repo.clone_from(
                        clone_url,
                        clone_dir,
                        bare=True,
                        depth=1,
                        branch=git_ref,
                        env=clone_env,
                    )
                except gitpython.exc.GitCommandError:
                    # depth/branch fails for commit hashes; retry with full bare clone
                    repo = gitpython.Repo.clone_from(clone_url, clone_dir, bare=True, env=clone_env)
            except gitpython.exc.GitCommandError as e:
                raise SyncError(
                    _("Failed to clone git repository '{url}': {error}").format(
                        url=remote.url, error=str(e)
                    )
                )
            await pb.aincrement()

        async with ProgressReport(message="Resolving Git ref", code="sync.git.resolving_ref") as pb:
            try:
                commit = repo.commit(git_ref)
            except (BadName, BadObject, ValueError, IndexError, NotImplementedError) as e:
                raise SyncError(
                    _("Could not resolve git ref '{ref}': {error}").format(
                        ref=git_ref, error=str(e)
                    )
                )
            await pb.aincrement()

        async with ProgressReport(
            message="Parsing Git tree",
            code="sync.git.parsing_tree",
        ) as pb:
            blobs = [item for item in commit.tree.traverse() if item.type == "blob"]
            lfs_blobs = {}
            pb.total = len(blobs)
            await pb.asave()

            for blob in blobs:
                relative_path = blob.path
                size = blob.size
                with tempfile.NamedTemporaryFile(dir=".", delete=False, mode="w+b") as file:
                    shutil.copyfileobj(blob.data_stream, file)
                    file.seek(0)
                    # Check to see if the blob is an LFS pointer
                    if size < 1024 and (lfs_tuple := self._parse_lfs_pointer(file.read())):
                        lfs_blobs[lfs_tuple[0]] = (relative_path, *lfs_tuple)
                        continue

                artifact = Artifact.init_and_validate(file.name, expected_size=size)
                file_content = FileContent(relative_path=relative_path, digest=artifact.sha256)
                da = DeclarativeArtifact(
                    artifact=artifact,
                    url=remote.url,
                    relative_path=relative_path,
                    remote=remote,
                    deferred_download=False,
                )
                dc = DeclarativeContent(content=file_content, d_artifacts=[da])
                await pb.aincrement()
                await self.put(dc)

            if lfs_blobs:
                lfs_results = await self._fetch_lfs_batch(lfs_blobs.values())
                for lfs_object in lfs_results.get("objects", []):
                    relative_path, oid, size = lfs_blobs[lfs_object["oid"]]
                    if lfs_object.get("error"):
                        raise SyncError(
                            _("Failed to resolve LFS blob '{rp}': {error}").format(
                                rp=relative_path, error=lfs_object.get("error", "Unknown error")
                            )
                        )
                    url = lfs_object["actions"]["download"]["href"]
                    artifact = Artifact(size=size, sha256=oid)
                    file_content = FileContent(relative_path=relative_path, digest=artifact.sha256)
                    if headers := lfs_object["actions"]["download"].get("header"):
                        extra_data = {"request_kwargs": {"headers": headers}}
                    else:
                        extra_data = None
                    da = DeclarativeArtifact(
                        artifact=artifact,
                        url=url,
                        relative_path=relative_path,
                        remote=remote,
                        deferred_download=False,
                        extra_data=extra_data,
                    )
                    dc = DeclarativeContent(content=file_content, d_artifacts=[da])
                    await pb.aincrement()
                    await self.put(dc)
