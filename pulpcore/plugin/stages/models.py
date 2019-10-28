from gettext import gettext as _

import asyncio

from pulpcore.plugin.models import Artifact


class DeclarativeArtifact:
    """
    Relates an :class:`~pulpcore.plugin.models.Artifact`, how to download it, and its
    `relative_path` used later during publishing.

    This is used by the Stages API stages to determine if an
    :class:`~pulpcore.plugin.models.Artifact` is already present and ensure Pulp can download it in
    the future. The `artifact` can be either saved or unsaved. If unsaved, the `artifact` attributes
    may be incomplete because not all digest information can be computed until the
    :class:`~pulpcore.plugin.models.Artifact` is downloaded.

    Attributes:
        artifact (:class:`~pulpcore.plugin.models.Artifact`): An
            :class:`~pulpcore.plugin.models.Artifact` either saved or unsaved. If unsaved, it
            may have partial digest information attached to it.
        url (str): the url to fetch the :class:`~pulpcore.plugin.models.Artifact` from.
        relative_path (str): the relative_path this :class:`~pulpcore.plugin.models.Artifact`
            should be published at for any Publication.
        remote (:class:`~pulpcore.plugin.models.Remote`): The remote used to fetch this
            :class:`~pulpcore.plugin.models.Artifact`.
        extra_data (dict): A dictionary available for additional data to be stored in.
        deferred_download (bool): Whether this artifact should be downloaded and saved
            in the artifact stages. Defaults to `False`. See :ref:`on-demand-support`.

    Raises:
        ValueError: If `artifact`, `url`, or `relative_path` are not specified. If `remote` is not
        specified and `artifact` doesn't have a file.
    """

    __slots__ = ('artifact', 'url', 'relative_path', 'remote',
                 'extra_data', 'deferred_download')

    def __init__(self, artifact=None, url=None, relative_path=None, remote=None, extra_data=None,
                 deferred_download=False):
        if not url:
            raise ValueError(_("DeclarativeArtifact must have a 'url'"))
        if not relative_path:
            raise ValueError(_("DeclarativeArtifact must have a 'relative_path'"))
        if not artifact:
            raise ValueError(_("DeclarativeArtifact must have a 'artifact'"))
        if not remote and not artifact.file:
            raise ValueError(_("DeclarativeArtifact must have a 'remote' if the Artifact doesn't "
                               "have a file backing it."))
        self.artifact = artifact
        self.url = url
        self.relative_path = relative_path
        self.remote = remote
        self.extra_data = extra_data or {}
        self.deferred_download = deferred_download

    async def download(self):
        """
        Download content and update the associated Artifact.

        Returns:
            Returns the :class:`~pulpcore.plugin.download.DownloadResult` of the Artifact.
        """
        expected_digests = {}
        validation_kwargs = {}
        for digest_name in self.artifact.DIGEST_FIELDS:
            digest_value = getattr(self.artifact, digest_name)
            if digest_value:
                expected_digests[digest_name] = digest_value
        if expected_digests:
            validation_kwargs['expected_digests'] = expected_digests
        if self.artifact.size:
            expected_size = self.artifact.size
            validation_kwargs['expected_size'] = expected_size
        downloader = self.remote.get_downloader(
            url=self.url,
            **validation_kwargs
        )
        # Custom downloaders may need extra information to complete the request.
        download_result = await downloader.run(extra_data=self.extra_data)
        self.artifact = Artifact(
            **download_result.artifact_attributes,
            file=download_result.path
        )
        return download_result


class DeclarativeContent:
    """
    Relates a Content unit and zero or more :class:`~pulpcore.plugin.stages.DeclarativeArtifact`
    objects.

    This is used by the Stages API stages to determine if a Content unit is already present and
    ensure all of its associated :class:`~pulpcore.plugin.stages.DeclarativeArtifact` objects are
    related correctly. The `content` can be either saved or unsaved depending on where in the Stages
    API pipeline this is used.

    Attributes:
        content (subclass of :class:`~pulpcore.plugin.models.Content`): A Content unit, possibly
            unsaved
        d_artifacts (list): A list of zero or more
            :class:`~pulpcore.plugin.stages.DeclarativeArtifact` objects associated with `content`.
        extra_data (dict): A dictionary available for additional data to be stored in.
        does_batch (bool): If `False`, prevent batching mechanism to block this item.
            Defaults to `True`.
        future (:class:`~asyncio.Future`): A future that gets resolved to the
            :class:`~pulpcore.plugin.models.Content` in the
            :class:`~pulpcore.plugin.stages.ResolveContentFutures` stage. See the
            :class:`~pulpcore.plugin.stages.ResolveContentFutures` stage for example usage.

    Raises:
        ValueError: If `content` is not specified.
    """

    __slots__ = ('content', 'd_artifacts', 'extra_data', 'does_batch', 'future')

    def __init__(self, content=None, d_artifacts=None, extra_data=None, does_batch=True):
        if not content:
            raise ValueError(_("DeclarativeContent must have a 'content'"))
        self.content = content
        self.d_artifacts = d_artifacts or []
        self.extra_data = extra_data or {}
        self.does_batch = does_batch
        self.future = None

    def get_or_create_future(self):
        """
        Return the existing or a new future.

        If you rely on this future in a the course of the pipeline, consider clearing the
        `does_batch` attribute to prevent deadlocks.
        See the :class:`~pulpcore.plugin.stages.ResolveContentFutures` stage for example usage.

        Returns:
            An existing :class:`asyncio.Future` or a newly created one.
        """
        if self.future is None:
            # If on 3.7, we could preferrably use get_running_loop()
            self.future = asyncio.get_event_loop().create_future()
        return self.future

    def __str__(self):
        return str(self.content.__class__.__name__)
