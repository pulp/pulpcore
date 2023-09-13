import asyncio
from collections import defaultdict
from gettext import gettext as _
import logging

from aiofiles import os as aos
from asgiref.sync import sync_to_async
from django.db.models import Prefetch, prefetch_related_objects, Q

from pulpcore.plugin.exceptions import UnsupportedDigestValidationError
from pulpcore.plugin.models import (
    AlternateContentSource,
    Artifact,
    ContentArtifact,
    ProgressReport,
    RemoteArtifact,
)
from pulpcore.plugin.sync import sync_to_async_iterable

from .api import Stage

log = logging.getLogger(__name__)


def _check_for_forbidden_checksum_type(artifact):
    """Check if content doesn't have forbidden checksum type.

    If contains forbidden checksum type it will raise ValueError,
    otherwise it passes without returning anything.
    """
    for digest_type in Artifact.FORBIDDEN_DIGESTS:
        digest_value = getattr(artifact, digest_type)
        if digest_value:
            # To use shared message constant when #7988 is merged
            raise UnsupportedDigestValidationError(
                _(
                    "Artifact contains forbidden checksum type {}. You can allow it with "
                    "'ALLOWED_CONTENT_CHECKSUMS' setting."
                ).format(digest_type)
            )


class QueryExistingArtifacts(Stage):
    """
    A Stages API stage that replaces :attr:`DeclarativeContent.content` objects with already-saved
    :class:`~pulpcore.plugin.models.Artifact` objects.

    This stage expects :class:`~pulpcore.plugin.stages.DeclarativeContent` units from `self._in_q`
    and inspects their associated :class:`~pulpcore.plugin.stages.DeclarativeArtifact` objects. Each
    :class:`~pulpcore.plugin.stages.DeclarativeArtifact` object stores one
    :class:`~pulpcore.plugin.models.Artifact`.

    This stage inspects any unsaved :class:`~pulpcore.plugin.models.Artifact` objects and searches
    using their metadata for existing saved :class:`~pulpcore.plugin.models.Artifact` objects inside
    Pulp with the same digest value(s). Any existing :class:`~pulpcore.plugin.models.Artifact`
    objects found will replace their unsaved counterpart in the
    :class:`~pulpcore.plugin.stages.DeclarativeArtifact` object.

    Each :class:`~pulpcore.plugin.stages.DeclarativeContent` is sent to `self._out_q` after all of
    its :class:`~pulpcore.plugin.stages.DeclarativeArtifact` objects have been handled.

    This stage drains all available items from `self._in_q` and batches everything into one large
    call to the db for efficiency.
    """

    async def run(self):
        """
        The coroutine for this stage.

        Returns:
            The coroutine for this stage.
        """
        async for batch in self.batches():
            artifact_digests_by_type = defaultdict(list)

            # For each unsaved artifact, check its digests in the order of COMMON_DIGEST_FIELDS
            # and the first digest which is found is added to the list of digests of that type.
            # We assume that in general only one digest is provided and that it will be
            # sufficient to identify the Artifact.
            for d_content in batch:
                for d_artifact in d_content.d_artifacts:
                    if d_artifact.artifact._state.adding:
                        if not d_artifact.deferred_download:
                            _check_for_forbidden_checksum_type(d_artifact.artifact)
                        for digest_type in Artifact.COMMON_DIGEST_FIELDS:
                            digest_value = getattr(d_artifact.artifact, digest_type)
                            if digest_value:
                                artifact_digests_by_type[digest_type].append(digest_value)
                                break

            # For each type of digest, fetch all the existing Artifacts where digest "in"
            # the list we built earlier. Walk over all the artifacts again compare the
            # digest of the new artifact to those of the existing ones - if one matches,
            # swap it out with the existing one.
            for digest_type, digests in artifact_digests_by_type.items():
                query_params = {
                    "{attr}__in".format(attr=digest_type): digests,
                    "pulp_domain": self.domain,
                }
                existing_artifacts_qs = Artifact.objects.filter(**query_params)
                existing_artifacts = sync_to_async_iterable(existing_artifacts_qs)
                await sync_to_async(existing_artifacts_qs.touch)()
                for d_content in batch:
                    for d_artifact in d_content.d_artifacts:
                        artifact_digest = getattr(d_artifact.artifact, digest_type)
                        if artifact_digest:
                            async for result in existing_artifacts:
                                result_digest = getattr(result, digest_type)
                                if result_digest == artifact_digest:
                                    d_artifact.artifact = result
                                    break
            for d_content in batch:
                await self.put(d_content)


class GenericDownloader(Stage):
    """
    A base Stages API stage to download files.

    This stage creates a ProgressReport named `PROGRESS_REPORTING_MESSAGE` that counts the number of
    downloads completed. Since it's a stream the total count isn't known until it's finished.

    This stage drains all available items from `self._in_q` and starts as many concurrent
    downloading tasks as possible, up to the limit defined by ``self.max_concurrent_content``.

    Each :class:`~pulpcore.plugin.stages.DeclarativeContent` is sent to `_handle_content_unit`,
    which must be implemented by the subclass, to handle processing the content unit and starting
    the downloads. After the downloads for that unit are complete the content should put into
    `self._out_q` to move onto the next stage.

    Args:
        max_concurrent_content (int): The maximum number of
            :class:`~pulpcore.plugin.stages.DeclarativeContent` instances to handle simultaneously.
            Default is 200.
        args: unused positional arguments passed along to :class:`~pulpcore.plugin.stages.Stage`.
        kwargs: unused keyword arguments passed along to :class:`~pulpcore.plugin.stages.Stage`.
    """

    PROGRESS_REPORTING_MESSAGE = "Downloading"
    PROGRESS_REPORTING_CODE = "sync.downloading"

    def __init__(self, max_concurrent_content=200, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.max_concurrent_content = max_concurrent_content

    async def run(self):
        """
        The coroutine for this stage.

        Returns:
            The coroutine for this stage.
        """

        def _add_to_pending(coro):
            nonlocal pending
            task = asyncio.ensure_future(coro)
            pending.add(task)
            return task

        #: (set): The set of unfinished tasks.  Contains the content
        #    handler tasks and may contain `content_get_task`.
        pending = set()

        content_iterator = self.items()

        #: (:class:`asyncio.Task`): The task that gets new content from `self._in_q`.
        #    Set to None if stage is shutdown.
        content_get_task = _add_to_pending(content_iterator.__anext__())

        async with ProgressReport(
            message=self.PROGRESS_REPORTING_MESSAGE, code=self.PROGRESS_REPORTING_CODE
        ) as pb:
            self.progress_report = pb
            try:
                while pending:
                    done, pending = await asyncio.wait(pending, return_when=asyncio.FIRST_COMPLETED)
                    for task in done:
                        if task is content_get_task:
                            try:
                                _add_to_pending(self._handle_content_unit(task.result()))
                            except StopAsyncIteration:
                                # previous stage is finished and we retrieved all
                                # content instances: shutdown
                                content_get_task = None
                        else:
                            pb.done += task.result()  # download_count
                            await pb.asave()

                    if content_get_task and content_get_task not in pending:  # not yet shutdown
                        if len(pending) < self.max_concurrent_content:
                            content_get_task = _add_to_pending(content_iterator.__anext__())
            except asyncio.CancelledError:
                # asyncio.wait does not cancel its tasks when cancelled, we need to do this
                for future in pending:
                    future.cancel()
                raise

    async def _handle_content_unit(self, d_content):
        """Handle one content unit.

        Must be implemented in subclasses.

        Returns:
            The number of downloads
        """
        raise NotImplementedError


class ArtifactDownloader(GenericDownloader):
    """
    A Stages API stage to download :class:`~pulpcore.plugin.models.Artifact` files, but don't save
    the :class:`~pulpcore.plugin.models.Artifact` in the db.

    This stage downloads the file for any :class:`~pulpcore.plugin.models.Artifact` objects missing
    files and creates a new :class:`~pulpcore.plugin.models.Artifact` object from the downloaded
    file and its digest data. The new :class:`~pulpcore.plugin.models.Artifact` is not saved but
    added to the :class:`~pulpcore.plugin.stages.DeclarativeArtifact` object, replacing the likely
    incomplete :class:`~pulpcore.plugin.models.Artifact`.

    Each :class:`~pulpcore.plugin.stages.DeclarativeContent` is sent to `self._out_q` after all of
    its :class:`~pulpcore.plugin.stages.DeclarativeArtifact` objects have been handled.
    """

    PROGRESS_REPORTING_MESSAGE = "Downloading Artifacts"
    PROGRESS_REPORTING_CODE = "sync.downloading.artifacts"

    async def _handle_content_unit(self, d_content):
        """Handle one content unit.

        Returns:
            The number of downloads
        """
        downloaders_for_content = [
            d_artifact.download()
            for d_artifact in d_content.d_artifacts
            if d_artifact.artifact._state.adding
            and not d_artifact.deferred_download
            and not d_artifact.artifact.file
        ]
        if downloaders_for_content:
            await asyncio.gather(*downloaders_for_content)
        await self.put(d_content)
        return len(downloaders_for_content)


class ArtifactSaver(Stage):
    """
    A Stages API stage that saves any unsaved :attr:`DeclarativeArtifact.artifact` objects.

    This stage expects :class:`~pulpcore.plugin.stages.DeclarativeContent` units from `self._in_q`
    and inspects their associated :class:`~pulpcore.plugin.stages.DeclarativeArtifact` objects. Each
    :class:`~pulpcore.plugin.stages.DeclarativeArtifact` object stores one
    :class:`~pulpcore.plugin.models.Artifact`.

    Any unsaved :class:`~pulpcore.plugin.models.Artifact` objects are saved. Each
    :class:`~pulpcore.plugin.stages.DeclarativeContent` is sent to `self._out_q` after all of its
    :class:`~pulpcore.plugin.stages.DeclarativeArtifact` objects have been handled.

    This stage drains all available items from `self._in_q` and batches everything into one large
    call to the db for efficiency.
    """

    async def run(self):
        """
        The coroutine for this stage.

        Returns:
            The coroutine for this stage.
        """
        async for batch in self.batches():
            da_to_save = []
            for d_content in batch:
                for d_artifact in d_content.d_artifacts:
                    if d_artifact.artifact._state.adding and not d_artifact.deferred_download:
                        d_artifact.artifact.file = str(d_artifact.artifact.file)
                        da_to_save.append(d_artifact)
            da_to_save_ordered = sorted(da_to_save, key=lambda x: x.artifact.sha256)
            da_tmp_files = [str(da.artifact.file) for da in da_to_save_ordered]

            if da_to_save:
                for d_artifact, artifact, tmp_file_path in zip(
                    da_to_save_ordered,
                    await sync_to_async(Artifact.objects.bulk_get_or_create)(
                        d_artifact.artifact for d_artifact in da_to_save_ordered
                    ),
                    da_tmp_files,
                ):
                    d_artifact.artifact = artifact
                    # Delete the downloaded tmp file if it still exists to clear up space
                    if await aos.path.exists(tmp_file_path):
                        await aos.remove(tmp_file_path)

            for d_content in batch:
                await self.put(d_content)


class RemoteArtifactSaver(Stage):
    """
    A Stage that saves :class:`~pulpcore.plugin.models.RemoteArtifact` objects

    An :class:`~pulpcore.plugin.models.RemoteArtifact` object is saved for each
    :class:`~pulpcore.plugin.stages.DeclarativeArtifact`.
    """

    def __init__(self, fix_mismatched_remote_artifacts=False, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fix_mismatched_remote_artifacts = fix_mismatched_remote_artifacts

    async def run(self):
        """
        The coroutine for this stage.

        Returns:
            The coroutine for this stage.
        """
        async for batch in self.batches():
            await self._handle_remote_artifacts(batch)
            for d_content in batch:
                await self.put(d_content)

    async def _handle_remote_artifacts(self, batch):
        """
        Build a list of only :class:`~pulpcore.plugin.models.RemoteArtifact` that need
        to be created for the batch.

        Args:
            batch (list): List of :class:`~pulpcore.plugin.stages.DeclarativeContent`.

        Returns:
            List: Of :class:`~pulpcore.plugin.models.RemoteArtifact`.
        """
        remotes_present = set()
        for d_content in batch:
            # https://code.djangoproject.com/ticket/33596
            # If the content was pre-fetched previously, remove that cached data, which could be out
            # of date.
            if hasattr(d_content.content, "_remote_artifact_saver_cas"):
                delattr(d_content.content, "_remote_artifact_saver_cas")
            for d_artifact in d_content.d_artifacts:
                if d_artifact.remote:
                    remotes_present.add(d_artifact.remote)

        await sync_to_async(prefetch_related_objects)(
            [d_c.content for d_c in batch],
            Prefetch(
                "contentartifact_set",
                queryset=ContentArtifact.objects.prefetch_related(
                    Prefetch(
                        "remoteartifact_set",
                        queryset=RemoteArtifact.objects.filter(remote__in=remotes_present),
                        to_attr="_remote_artifact_saver_ras",
                    )
                ),
                to_attr="_remote_artifact_saver_cas",
            ),
        )

        # Now return the list of RemoteArtifacts that need to be saved.
        #
        # We can end up with duplicates (diff pks, same sha256) in the sequence below,
        # so we store by-sha256 and then return the final values
        ras_to_create = {}  # { str(<sha256>): RemoteArtifact, ... }
        ras_to_update = {}
        for d_content in batch:
            for d_artifact in d_content.d_artifacts:
                if not d_artifact.remote:
                    continue

                async for content_artifact in sync_to_async_iterable(
                    d_content.content._remote_artifact_saver_cas
                ):
                    if d_artifact.relative_path == content_artifact.relative_path:
                        break
                else:
                    if self.fix_mismatched_remote_artifacts:
                        # We couldn't match an DeclarativeArtifact to a ContentArtifact by rel_path.
                        # If there are any paths available (i.e., other ContentArtifacts for this
                        # Artifact), complain to the logs, pick the rel_path from the last
                        # ContentArtifact we examined, and continue.
                        #
                        # If we can't find anything to choose from (can that even happen?), fail
                        # the process.
                        avail_paths = ",".join(
                            [
                                ca.relative_path
                                for ca in d_content.content._remote_artifact_saver_cas
                            ]
                        )
                        if avail_paths:
                            msg = (
                                "No declared artifact with relative path '{rp}' for content '{c}'"
                                " from remote '{rname}'. Using last from available-paths : '{ap}'"
                            )
                            log.warning(
                                msg.format(
                                    rp=d_artifact.relative_path,
                                    c=d_content.content.natural_key(),
                                    rname=d_artifact.remote.name,
                                    ap=avail_paths,
                                )
                            )
                            d_artifact.relative_path = content_artifact.relative_path
                        else:
                            msg = _(
                                "No declared artifact with relative path '{rp}' for content '{c}'"
                                " from remote '{rname}', and no paths available."
                            )
                            raise ValueError(
                                msg.format(
                                    rp=d_artifact.relative_path,
                                    c=d_content.content.natural_key(),
                                    rname=d_artifact.remote.name,
                                )
                            )
                    else:
                        msg = _('No declared artifact with relative path "{rp}" for content "{c}"')
                        raise ValueError(
                            msg.format(rp=d_artifact.relative_path, c=d_content.content)
                        )

                async for remote_artifact in sync_to_async_iterable(
                    content_artifact._remote_artifact_saver_ras
                ):
                    if d_artifact.url == remote_artifact.url:
                        break

                    if d_artifact.remote.pk == remote_artifact.remote_id:
                        key = f"{content_artifact.pk}-{remote_artifact.remote_id}"
                        remote_artifact.url = d_artifact.url
                        ras_to_update[key] = remote_artifact
                        break
                else:
                    remote_artifact = self._create_remote_artifact(d_artifact, content_artifact)
                    key = f"{content_artifact.pk}-{d_artifact.remote.pk}"
                    ras_to_create[key] = remote_artifact

        # Make sure we create/update RemoteArtifacts in a stable order, to help
        # prevent deadlocks in high-concurrency environments. We can rely on the
        # Artifact sha256 for our ordering.
        if ras_to_create:
            ras_to_create_ordered = sorted(list(ras_to_create.values()), key=lambda x: x.sha256)
            await sync_to_async(RemoteArtifact.objects.bulk_create)(ras_to_create_ordered)
        if ras_to_update:
            ras_to_update_ordered = sorted(list(ras_to_update.values()), key=lambda x: x.sha256)
            await sync_to_async(RemoteArtifact.objects.bulk_update)(
                ras_to_update_ordered, fields=["url"]
            )

    @staticmethod
    def _create_remote_artifact(d_artifact, content_artifact):
        ra = RemoteArtifact(
            url=d_artifact.url,
            size=d_artifact.artifact.size,
            md5=d_artifact.artifact.md5,
            sha1=d_artifact.artifact.sha1,
            sha224=d_artifact.artifact.sha224,
            sha256=d_artifact.artifact.sha256,
            sha384=d_artifact.artifact.sha384,
            sha512=d_artifact.artifact.sha512,
            content_artifact=content_artifact,
            remote=d_artifact.remote,
        )
        ra.validate_checksums()
        return ra


class ACSArtifactHandler(Stage):
    """
    API stage to download :class:`~pulpcore.plugin.models.Artifact` files from Alternate
    Content Source if available.
    """

    async def run(self):
        async for batch in self.batches():
            acs_query = AlternateContentSource.objects.filter(pulp_domain=self.domain)
            acs_exists = await acs_query.aexists()
            if acs_exists:
                # Gather batch d_artifact checksums
                batch_checksums = defaultdict(list)
                for d_content in batch:
                    for d_artifact in d_content.d_artifacts:
                        for cks_type in d_artifact.artifact.COMMON_DIGEST_FIELDS:
                            if getattr(d_artifact.artifact, cks_type):
                                batch_checksums[cks_type].append(
                                    getattr(d_artifact.artifact, cks_type)
                                )

                batch_query = Q()
                for checksum_type in batch_checksums.keys():
                    batch_query.add(
                        Q(**{f"{checksum_type}__in": batch_checksums[checksum_type]}), Q.OR
                    )

                existing_ras = (
                    RemoteArtifact.objects.acs()
                    .filter(batch_query)
                    .only("url", "remote")
                    .select_related("remote")
                )
                existing_ras_dict = dict()
                async for ra in existing_ras:
                    for c_type in Artifact.COMMON_DIGEST_FIELDS:
                        checksum = await sync_to_async(getattr)(ra, c_type)
                        # pick the first occurence of RA from ACS
                        if checksum and checksum not in existing_ras_dict:
                            existing_ras_dict[checksum] = {
                                "remote": ra.remote,
                                "url": ra.url,
                            }

                for d_content in batch:
                    for d_artifact in d_content.d_artifacts:
                        for checksum_type in Artifact.COMMON_DIGEST_FIELDS:
                            if getattr(d_artifact.artifact, checksum_type):
                                checksum = getattr(d_artifact.artifact, checksum_type)
                                if checksum in existing_ras_dict:
                                    d_artifact.urls = [
                                        existing_ras_dict[checksum]["url"]
                                    ] + d_artifact.urls
                                    d_artifact.remote = existing_ras_dict[checksum]["remote"]

            for d_content in batch:
                await self.put(d_content)
