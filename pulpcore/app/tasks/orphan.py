import gc

from pulpcore.app.models import (
    Artifact,
    Content,
    ProgressReport,
    PublishedMetadata,
)


def queryset_iterator(qs, batchsize=2000, gc_collect=True):
    """
    Provide a batching functionality that returns individual querysets per batch.

    Copied from here with minor changes:
    https://www.guguweb.com/2020/03/27/optimize-django-memory-usage/
    """
    iterator = qs.values_list("pk", flat=True).order_by("pk").distinct().iterator()
    eof = False
    while not eof:
        primary_key_buffer = []
        try:
            while len(primary_key_buffer) < batchsize:
                primary_key_buffer.append(next(iterator))
        except StopIteration:
            eof = True
        yield qs.filter(pk__in=primary_key_buffer).order_by("pk")
        if gc_collect:
            gc.collect()


def orphan_cleanup(content_pks=None):
    """
    Delete all orphan Content and Artifact records.
    Go through orphan Content multiple times to remove content from subrepos.
    This task removes Artifact files from the filesystem as well.

    Kwargs:
        content_pks (list): A list of content pks. If specified, only remove these orphans.

    """
    progress_bar = ProgressReport(
        message="Clean up orphan Content",
        total=0,
        code="clean-up.content",
        done=0,
        state="running",
    )

    while True:
        content = Content.objects.filter(version_memberships__isnull=True).exclude(
            pulp_type=PublishedMetadata.get_pulp_type()
        )
        if content_pks:
            content = content.filter(pk__in=content_pks)

        content_count = content.count()
        if not content_count:
            break

        progress_bar.total += content_count
        progress_bar.save()

        # delete the content
        for c in queryset_iterator(content):
            progress_bar.increase_by(c.count())
            c.delete()

    progress_bar.state = "completed"
    progress_bar.save()

    # delete the artifacts that don't belong to any content
    artifacts = Artifact.objects.filter(content_memberships__isnull=True)

    progress_bar = ProgressReport(
        message="Clean up orphan Artifacts",
        total=artifacts.count(),
        code="clean-up.content",
        done=0,
        state="running",
    )
    progress_bar.save()

    counter = 0
    interval = 100
    for artifact in artifacts.iterator():
        # we need to manually call delete() because it cleans up the file on the filesystem
        artifact.delete()
        progress_bar.done += 1
        counter += 1

        if counter >= interval:
            progress_bar.save()
            counter = 0

    progress_bar.state = "completed"
    progress_bar.save()
