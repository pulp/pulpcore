from logging import getLogger

from django.db.models.deletion import ProtectedError

from pulpcore.app.models import (
    Artifact,
    Content,
    ContentArtifact,
    ProgressReport,
    PublishedMetadata,
    Repository,
    RepositoryVersion,
)
from pulpcore.app.util import get_domain

log = getLogger(__name__)


def reclaim_space(repo_pks, keeplist_rv_pks=None, force=False):
    """
    This task frees-up disk space by removing Artifact files from the filesystem for Content
    exclusive to the list of provided repos.

    Note: content marked as `proctected` will be excluded from the reclaim disk space.

    Kwargs:
        repo_pks (list): A list of repo pks the disk reclaim space is performed on.
        keeplist_rv_pks (list): A list of repo version pks that will be excluded from the reclaim
        disk space.
        force (bool): If True, uploaded content will be taken into account.

    """
    reclaimed_repos = Repository.objects.filter(pk__in=repo_pks)
    for repo in reclaimed_repos:
        repo.invalidate_cache(everything=True)

    domain = get_domain()
    rest_of_repos = Repository.objects.filter(pulp_domain=domain).exclude(pk__in=repo_pks)
    c_keep_qs = Content.objects.filter(repositories__in=rest_of_repos)
    c_reclaim_qs = Content.objects.filter(repositories__in=repo_pks)
    c_reclaim_qs = c_reclaim_qs.exclude(
        pk__in=c_keep_qs, pulp_type=PublishedMetadata.get_pulp_type()
    )

    if keeplist_rv_pks:
        rv_qs = RepositoryVersion.objects.filter(pk__in=keeplist_rv_pks)
        rv_content = Content.objects.none()
        for rv in rv_qs.iterator():
            rv_content |= rv.content
        c_reclaim_qs = c_reclaim_qs.exclude(pk__in=rv_content)

    content_distinct = c_reclaim_qs.distinct("pulp_type")
    unprotected = []
    for content in content_distinct:
        if not content.cast().PROTECTED_FROM_RECLAIM:
            unprotected.append(content.pulp_type)

    ca_qs = ContentArtifact.objects.select_related("content", "artifact").filter(
        content__in=c_reclaim_qs.values("pk"), artifact__isnull=False
    )
    if not force:
        ca_qs = ca_qs.filter(remoteartifact__isnull=False)
    artifact_pks = set()
    ca_to_update = []
    for ca in ca_qs.iterator():
        if ca.content.pulp_type in unprotected:
            artifact_pks.add(ca.artifact.pk)
            ca.artifact = None
            ca_to_update.append(ca)

    ContentArtifact.objects.bulk_update(objs=ca_to_update, fields=["artifact"], batch_size=1000)
    artifacts_to_delete = Artifact.objects.filter(pk__in=artifact_pks)
    progress_bar = ProgressReport(
        message="Reclaim disk space",
        total=artifacts_to_delete.count(),
        code="reclaim-space.artifact",
        done=0,
        state="running",
    )
    progress_bar.save()

    counter = 0
    interval = 100
    for artifact in artifacts_to_delete.iterator():
        try:
            # we need to manually call delete() because it cleans up the file on the filesystem
            artifact.delete()
        except ProtectedError as e:
            # Rarely artifact could be shared between two different content units.
            # Just log and skip the artifact deletion in this case
            log.debug(e)
        else:
            progress_bar.done += 1
            counter += 1

        if counter >= interval:
            progress_bar.save()
            counter = 0

    progress_bar.state = "completed"
    progress_bar.save()
