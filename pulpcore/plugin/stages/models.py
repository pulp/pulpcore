from gettext import gettext as _

import asyncio

from pulpcore.constants import ALL_KNOWN_CONTENT_CHECKSUMS
from pulpcore.plugin.models import Artifact


class DeclarativeArtifact:
    """
    Relates an [pulpcore.plugin.models.Artifact][], how to download it, and its
    `relative_path` used later during publishing.

    This is used by the Stages API stages to determine if an
    [pulpcore.plugin.models.Artifact][] is already present and ensure Pulp can download it in
    the future. The `artifact` can be either saved or unsaved. If unsaved, the `artifact` attributes
    may be incomplete because not all digest information can be computed until the
    [pulpcore.plugin.models.Artifact][] is downloaded.

    Attributes:
        artifact (pulpcore.plugin.models.Artifact) An
            [pulpcore.plugin.models.Artifact][] either saved or unsaved. If unsaved, it
            may have partial digest information attached to it.
        url (str): the url to fetch the [pulpcore.plugin.models.Artifact][] from.
        urls (List[str]): A list of many possible URLs to fetch the
            [pulpcore.plugin.models.Artifact][] from.
        relative_path (str): the relative_path this [pulpcore.plugin.models.Artifact][]
            should be published at for any Publication.
        remote (pulpcore.plugin.models.Remote) The remote used to fetch this
            [pulpcore.plugin.models.Artifact][].
        extra_data (dict): A dictionary available for additional data to be stored in.
        deferred_download (bool): Whether this artifact should be downloaded and saved
            in the artifact stages. Defaults to `False`. See :ref:`on-demand-support`.

    Raises:
        ValueError: If `artifact`, `url`, or `relative_path` are not specified. If `remote` is not
        specified and `artifact` doesn't have a file.
    """

    __slots__ = (
        "artifact",
        "urls",
        "relative_path",
        "remote",
        "extra_data",
        "deferred_download",
    )

    def __init__(
        self,
        artifact=None,
        url=None,
        urls=None,
        relative_path=None,
        remote=None,
        extra_data=None,
        deferred_download=False,
    ):
        if not (url or urls):
            raise ValueError(_("DeclarativeArtifact must have a at least one 'url' provided"))
        if url and urls:
            raise ValueError(_("DeclarativeArtifact must not provide both 'url' and 'urls'"))
        if not relative_path:
            raise ValueError(_("DeclarativeArtifact must have a 'relative_path'"))
        if not artifact:
            raise ValueError(_("DeclarativeArtifact must have a 'artifact'"))
        if not remote and not artifact.file:
            raise ValueError(
                _(
                    "DeclarativeArtifact must have a 'remote' if the Artifact doesn't "
                    "have a file backing it."
                )
            )
        self.artifact = artifact
        self.urls = [url] if url else urls
        self.relative_path = relative_path
        self.remote = remote
        self.extra_data = extra_data or {}
        self.deferred_download = deferred_download

    @property
    def url(self):
        return self.urls[0]

    async def download(self):
        """
        Download content and update the associated Artifact.

        Returns:
            Returns the [pulpcore.plugin.download.DownloadResult][] of the Artifact.
        """
        expected_digests = {}
        validation_kwargs = {}
        for digest_name in ALL_KNOWN_CONTENT_CHECKSUMS:
            digest_value = getattr(self.artifact, digest_name)
            if digest_value:
                expected_digests[digest_name] = digest_value
        if expected_digests:
            validation_kwargs["expected_digests"] = expected_digests
        if self.artifact.size:
            expected_size = self.artifact.size
            validation_kwargs["expected_size"] = expected_size

        urls = iter(self.urls)
        url = next(urls)

        while True:
            downloader = self.remote.get_downloader(url=url, **validation_kwargs)
            try:
                # Custom downloaders may need extra information to complete the request.
                download_result = await downloader.run(extra_data=self.extra_data)
            except Exception as e:
                if url := next(urls, None):
                    # If there's more mirrors to try, ignore the error and move on
                    continue
                else:
                    # There's no more mirrors to try, we need to raise the error instead of
                    # swallowing it
                    raise e
            self.artifact = Artifact(
                **download_result.artifact_attributes, file=download_result.path
            )
            return download_result


class DeclarativeContent:
    """
    Relates a Content unit and zero or more [pulpcore.plugin.stages.DeclarativeArtifact][]
    objects.

    This is used by the Stages API stages to determine if a Content unit is already present and
    ensure all of its associated [pulpcore.plugin.stages.DeclarativeArtifact][] objects are
    related correctly. The `content` can be either saved or unsaved depending on where in the Stages
    API pipeline this is used.

    Attributes:
        content (subclass of [pulpcore.plugin.models.Content][]): A Content unit, possibly
            unsaved
        d_artifacts (list): A list of zero or more
            [pulpcore.plugin.stages.DeclarativeArtifact][] objects associated with `content`.
        extra_data (dict): A dictionary available for additional data to be stored in.

    Raises:
        ValueError: If `content` is not specified.
    """

    __slots__ = (
        "content",
        "d_artifacts",
        "extra_data",
        "_future",
        "_thaw_queue_event",
        "_resolved",
    )

    def __init__(self, content=None, d_artifacts=None, extra_data=None):
        if not content:
            raise ValueError(_("DeclarativeContent must have a 'content'"))
        self.content = content
        self.d_artifacts = d_artifacts or []
        self.extra_data = extra_data or {}
        self._future = None
        self._thaw_queue_event = None
        self._resolved = False

    @property
    def does_batch(self):
        """Whether this content is being awaited on and must therefore not wait forever in batches.
        When overwritten in subclasses, a `True` value must never be turned into `False`.
        """
        return self._resolved or self._future is None

    async def resolution(self):
        """Coroutine that waits for the content to be saved to database.
        Returns the content unit."""
        if self._resolved:
            # Already resolved ~> shortcut
            return self.content
        if self._future is None:
            # We do not yet have a future
            self._future = asyncio.get_event_loop().create_future()
            if self._thaw_queue_event:
                # We have a future now but are still stuck in a queue
                self._thaw_queue_event.set()
        # Now we wait
        return await self._future

    def resolve(self):
        """Resolve this content unit and notify any waiting tasks."""
        self._resolved = True
        if self._future:
            self._future.set_result(self.content)
            self._future = None

    def __str__(self):
        return str(self.content.__class__.__name__)
