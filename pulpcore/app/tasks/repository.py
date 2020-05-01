from gettext import gettext as _
from logging import getLogger
from functools import partial
import asyncio
import hashlib

from django.db import transaction

from pulpcore.app import models

log = getLogger(__name__)


def delete_version(pk):
    """
    Delete a repository version by squashing its changes with the next newer version. This ensures
    that the content set for each version stays the same.

    There must be a newer version to squash into. If we deleted the latest version, the next content
    change would create a new one of the same number, which would violate the immutability
    guarantee.

    Args:
        pk (uuid): the primary key for a RepositoryVersion to delete

    Raises:
        models.RepositoryVersion.DoesNotExist: if there is not a newer version to squash into.
            TODO: something more friendly
    """
    with transaction.atomic():
        try:
            version = models.RepositoryVersion.objects.get(pk=pk)
        except models.RepositoryVersion.DoesNotExist:
            log.info(_("The repository version was not found. Nothing to do."))
            return

        log.info(
            _("Deleting and squashing version %(v)d of repository %(r)s"),
            {"v": version.number, "r": version.repository.name},
        )

        version.delete()


async def _repair_ca(content_artifact, repaired=None):
    for remote_artifact in content_artifact.remoteartifact_set.all():
        downloader = remote_artifact.remote.get_downloader(remote_artifact)
        dl_result = await downloader.run()
        if dl_result.artifact_attributes["sha256"] == content_artifact.artifact.sha256:
            with open(dl_result.path, "rb") as src:
                filename = content_artifact.artifact.file.name
                content_artifact.artifact.file.delete(save=False)
                content_artifact.artifact.file.save(filename, src, save=False)
            if repaired is not None:
                repaired.increment()
            return True
        log.warn(_("Redownload failed from {}.").format(remote_artifact.url))
    return False


def _verify_ca(content_artifact):
    try:
        # verify files digest
        hasher = hashlib.sha256()
        for chunk in iter(lambda: content_artifact.artifact.file.read(1024 * 1024), b""):
            hasher.update(chunk)
        return hasher.hexdigest() == content_artifact.artifact.sha256
    except FileNotFoundError:
        return False


async def _repair_repository_version(version):
    loop = asyncio.get_event_loop()
    pending = set()
    with models.ProgressReport(
        message="Identify corrupted units", code="repair.corrupted"
    ) as corrupted:
        with models.ProgressReport(
            message="Repair corrupted units", code="repair.repaired"
        ) as repaired:
            query_set = models.ContentArtifact.objects.filter(
                content__in=version.content
            ).prefetch_related("artifact")
            for content_artifact in query_set:
                if not content_artifact.artifact:
                    continue
                if not await loop.run_in_executor(None, partial(_verify_ca, content_artifact)):
                    corrupted.increment()
                    log.warn(_("Digest mismatch for {}").format(content_artifact))
                    if len(pending) >= 5:  # Limit the number of concurrent repair tasks
                        done, pending = await asyncio.wait(
                            pending, return_when=asyncio.FIRST_COMPLETED
                        )
                        await asyncio.gather(*done)  # Clean up tasks
                    pending.add(asyncio.ensure_future(_repair_ca(content_artifact, repaired)))
            await asyncio.gather(*pending)


def repair_version(repository_version_pk):
    """
    Repair the artifacts associated with this repository version.

    Artifact files that have suffered from bit rot, were altered or have gone missing will be
    attempted to be refetched fron an associated upstream.

    Args:
        repository_version_pk (uuid): the primary key for a RepositoryVersion to delete
    """

    version = models.RepositoryVersion.objects.get(pk=repository_version_pk)

    log.info(
        _("Repairing version %(v)d of repository %(r)s"),
        {"v": version.number, "r": version.repository.name},
    )

    loop = asyncio.get_event_loop()
    loop.run_until_complete(_repair_repository_version(version))


def add_and_remove(repository_pk, add_content_units, remove_content_units, base_version_pk=None):
    """
    Create a new repository version by adding and then removing content units.

    Args:
        repository_pk (int): The primary key for a Repository for which a new Repository Version
            should be created.
        add_content_units (list): List of PKs for :class:`~pulpcore.app.models.Content` that
            should be added to the previous Repository Version for this Repository.
        remove_content_units (list): List of PKs for:class:`~pulpcore.app.models.Content` that
            should be removed from the previous Repository Version for this Repository.
        base_version_pk (int): the primary key for a RepositoryVersion whose content will be used
            as the initial set of content for our new RepositoryVersion
    """
    repository = models.Repository.objects.get(pk=repository_pk).cast()

    if base_version_pk:
        base_version = models.RepositoryVersion.objects.get(pk=base_version_pk)
    else:
        base_version = None

    if "*" in remove_content_units:
        latest = repository.latest_version()
        if latest:
            remove_content_units = latest.content.values_list("pk", flat=True)
        else:
            remove_content_units = []

    with repository.new_version(base_version=base_version) as new_version:
        new_version.remove_content(models.Content.objects.filter(pk__in=remove_content_units))
        new_version.add_content(models.Content.objects.filter(pk__in=add_content_units))
