from collections import defaultdict

from asgiref.sync import sync_to_async
from django.core.exceptions import ObjectDoesNotExist
from django.db import IntegrityError, transaction
from django.db.models import Q

from pulpcore.plugin.sync import sync_to_async_iterable

from pulpcore.plugin.models import Content, ContentArtifact, ProgressReport

from .api import Stage


class QueryExistingContents(Stage):
    """
    A Stages API stage that saves :attr:`DeclarativeContent.content` objects and saves its related
    [pulpcore.plugin.models.ContentArtifact][] objects too.

    This stage expects [pulpcore.plugin.stages.DeclarativeContent][] units from `self._in_q`
    and inspects their associated [pulpcore.plugin.stages.DeclarativeArtifact][] objects. Each
    [pulpcore.plugin.stages.DeclarativeArtifact][] object stores one
    [pulpcore.plugin.models.Artifact][].

    This stage inspects any "unsaved" Content unit objects and searches for existing saved Content
    units inside Pulp with the same unit key. Any existing Content objects found, replace their
    "unsaved" counterpart in the [pulpcore.plugin.stages.DeclarativeContent][] object.

    Each [pulpcore.plugin.stages.DeclarativeContent][] is sent to `self._out_q` after it has
    been handled.

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
            content_q_by_type = defaultdict(lambda: Q(pk__in=[]))
            d_content_by_nat_key = defaultdict(list)
            for d_content in batch:
                if d_content.content._state.adding:
                    model_type = type(d_content.content)
                    unit_q = d_content.content.q()
                    content_q_by_type[model_type] = content_q_by_type[model_type] | unit_q
                    d_content_by_nat_key[d_content.content.natural_key()].append(d_content)

            for model_type, content_q in content_q_by_type.items():
                try:
                    await sync_to_async(model_type.objects.filter(content_q).touch)()
                except AttributeError:
                    raise TypeError(
                        "Plugins which declare custom ORM managers on their content classes "
                        "should have those managers inherit from "
                        "pulpcore.plugin.models.ContentManager."
                    )
                async for result in sync_to_async_iterable(
                    model_type.objects.filter(content_q).iterator()
                ):
                    for d_content in d_content_by_nat_key[result.natural_key()]:
                        d_content.content = result

            for d_content in batch:
                await self.put(d_content)


class ContentSaver(Stage):
    """
    A Stages API stage that saves :attr:`DeclarativeContent.content` objects and saves its related
    [pulpcore.plugin.models.ContentArtifact][] objects too.

    This stage expects [pulpcore.plugin.stages.DeclarativeContent][] units from `self._in_q`
    and inspects their associated [pulpcore.plugin.stages.DeclarativeArtifact][] objects. Each
    [pulpcore.plugin.stages.DeclarativeArtifact][] object stores one
    [pulpcore.plugin.models.Artifact][].

    Each "unsaved" Content objects is saved and a [pulpcore.plugin.models.ContentArtifact][]
    objects too.

    Each [pulpcore.plugin.stages.DeclarativeContent][] is sent to after it has been handled.

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

            def process_batch():
                content_artifact_bulk = []
                to_update_ca_query = ContentArtifact.objects.none()
                to_update_ca_bulk = []
                to_update_ca_artifact = {}
                with transaction.atomic():
                    self._pre_save(batch)
                    # Process the batch in dc.content.natural_keys order.
                    # This prevents deadlocks when we're processing the same/similar content
                    # in concurrent workers.
                    batch.sort(key=lambda x: "".join(map(str, x.content.natural_key())))
                    for d_content in batch:
                        # Are we saving to the database for the first time?
                        content_already_saved = not d_content.content._state.adding
                        if not content_already_saved:
                            try:
                                with transaction.atomic():
                                    d_content.content.save()
                            except IntegrityError as e:
                                try:
                                    d_content.content = d_content.content.__class__.objects.get(
                                        d_content.content.q()
                                    )
                                except ObjectDoesNotExist:
                                    raise e
                            else:
                                for d_artifact in d_content.d_artifacts:
                                    if not d_artifact.artifact._state.adding:
                                        artifact = d_artifact.artifact
                                    else:
                                        # set to None for on-demand synced artifacts
                                        artifact = None
                                    content_artifact = ContentArtifact(
                                        content=d_content.content,
                                        artifact=artifact,
                                        relative_path=d_artifact.relative_path,
                                    )
                                    content_artifact_bulk.append(content_artifact)
                                continue
                        # When the Content already exists, check if ContentArtifacts need to be
                        # updated
                        for d_artifact in d_content.d_artifacts:
                            if not d_artifact.artifact._state.adding:
                                # the artifact is already present in the database; update references
                                # Creating one large query and one large dictionary
                                to_update_ca_query |= ContentArtifact.objects.filter(
                                    content=d_content.content,
                                    relative_path=d_artifact.relative_path,
                                )
                                key = (d_content.content.pk, d_artifact.relative_path)
                                to_update_ca_artifact[key] = d_artifact.artifact

                    # Query db once and update each object in memory for bulk_update call
                    for content_artifact in to_update_ca_query.iterator():
                        key = (content_artifact.content_id, content_artifact.relative_path)
                        # Same content/relpath/artifact-sha means no change to the
                        # contentartifact, ignore. This prevents us from colliding with any
                        # concurrent syncs with overlapping identical content. "Someone" updated
                        # the contentartifacts to match what we would be doing, so we don't need
                        # to do an (unnecessary) db-update, which was opening us up for a variety
                        # of potential deadlock scenarios.
                        #
                        # We start knowing that we're comparing CAs with same content/rel-path,
                        # because that's what we're using for the key to look up the incoming CA.
                        # So now let's compare artifacts, incoming vs current.
                        #
                        # Are we changing from no-artifact to having one or vice-versa?
                        artifact_state_change = bool(content_artifact.artifact) ^ bool(
                            to_update_ca_artifact[key]
                        )
                        # Do both current and incoming have an artifact?
                        both_have_artifact = (
                            content_artifact.artifact and to_update_ca_artifact[key]
                        )
                        # If both sides have an artifact, do they have the same sha256?
                        same_artifact_hash = both_have_artifact and (
                            content_artifact.artifact.sha256 == to_update_ca_artifact[key].sha256
                        )
                        # Only update if there was an actual change
                        if artifact_state_change or (both_have_artifact and not same_artifact_hash):
                            content_artifact.artifact = to_update_ca_artifact[key]
                            to_update_ca_bulk.append(content_artifact)

                    # to_update_ca_bulk are the CAs that we know are already persisted.
                    # We need to update their artifact_ids, and wish to do it in bulk to
                    # avoid hundreds of round-trips to the database.
                    if to_update_ca_bulk:
                        ContentArtifact.objects.bulk_update(to_update_ca_bulk, ["artifact"])

                    # To avoid a deadlock issue when calling get_or_create, we sort the
                    # "new" CAs to make sure inserts happen in a defined order. Since we can't
                    # trust the pulp_id (by the time we go to create a CA, it may already exist,
                    # and be replaced by the 'real' one), we sort by their "natural key".
                    content_artifact_bulk.sort(key=lambda x: ContentArtifact.sort_key(x))
                    ContentArtifact.objects.bulk_get_or_create(content_artifact_bulk)

                    self._post_save(batch)

            await sync_to_async(process_batch)()
            for declarative_content in batch:
                await self.put(declarative_content)

    def _pre_save(self, batch):
        """
        A hook plugin-writers can override to save related objects prior to content unit saving.

        This is run within the same transaction as the content unit saving.

        Args:
            batch (list of [pulpcore.plugin.stages.DeclarativeContent][]): The batch of
                [pulpcore.plugin.stages.DeclarativeContent][] objects to be saved.

        """
        pass

    def _post_save(self, batch):
        """
        A hook plugin-writers can override to save related objects after content unit saving.

        This is run within the same transaction as the content unit saving.

        Args:
            batch (list of [pulpcore.plugin.stages.DeclarativeContent][]): The batch of
                [pulpcore.plugin.stages.DeclarativeContent][] objects to be saved.

        """
        pass


class ResolveContentFutures(Stage):
    """
    This stage resolves the futures in [pulpcore.plugin.stages.DeclarativeContent][].

    Futures results are set to the found/created [pulpcore.plugin.models.Content][].

    This is useful when data downloaded from the plugin API needs to be parsed by FirstStage to
    create additional [pulpcore.plugin.stages.DeclarativeContent][] objects to be send down
    the pipeline. Consider an example where content type `Foo` references additional instances of a
    different content type `Bar`. Consider this code in FirstStage::

        # Create d_content and d_artifact for a `foo_a`
        foo_a = DeclarativeContent(...)
        # Send it in the pipeline
        await self.put(foo_a)

        ...

        foo_a_content = await foo_a.resolution()  # awaits until the foo_a reaches this stage

    This creates a "looping" pattern, of sorts, where downloaded content at the end of the pipeline
    can introduce new additional to-be-downloaded content at the beginning of the pipeline.
    On the other hand, it can impose a substantial performance decrement of batching content in the
    earlier stages.
    If you want to drop a declarative content prematurely from the pipeline, use the function
    `resolve()` to unblock the coroutines awaiting the attached future and do not hand the content
    to the next stage.
    As a rule of thumb, sending more items into the pipeline first and awaiting their resolution
    later is better.
    """

    async def run(self):
        """
        The coroutine for this stage.

        Returns:
            The coroutine for this stage.
        """
        async for d_content in self.items():
            d_content.resolve()
            await self.put(d_content)


class ContentAssociation(Stage):
    """
    A Stages API stage that associates content units with `new_version`.

    This stage stores all content unit primary keys in memory before running. This is done to
    compute the units already associated but not received from `self._in_q`. These units are passed
    via `self._out_q` to the next stage as a [django.db.models.query.QuerySet][].

    This stage creates a ProgressReport named 'Associating Content' that counts the number of units
    associated. Since it's a stream the total count isn't known until it's finished.

    If `mirror` was enabled, then content units may also be un-assocated (removed) from
    `new_version`. A ProgressReport named 'Un-Associating Content' is created that counts the number
    of units un-associated.

    Args:
        new_version (pulpcore.plugin.models.RepositoryVersion) The repo version this
            stage associates content with.
        mirror (bool): Whether or not to "mirror" the stream of DeclarativeContent - whether content
            not in the stream should be removed from the repository.
        args: unused positional arguments passed along to [pulpcore.plugin.stages.Stage][].
        kwargs: unused keyword arguments passed along to [pulpcore.plugin.stages.Stage][].
    """

    def __init__(self, new_version, mirror, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.new_version = new_version
        self.allow_delete = mirror

    async def run(self):
        """
        The coroutine for this stage.

        Returns:
            The coroutine for this stage.
        """
        async with ProgressReport(message="Associating Content", code="associating.content") as pb:
            to_delete = {
                i
                async for i in sync_to_async_iterable(
                    self.new_version.content.values_list("pk", flat=True)
                )
            }

            async for batch in self.batches():
                to_add = set()
                for d_content in batch:
                    try:
                        to_delete.remove(d_content.content.pk)
                    except KeyError:
                        to_add.add(d_content.content.pk)
                        await self.put(d_content)

                if to_add:
                    await sync_to_async(self.new_version.add_content)(
                        Content.objects.filter(pk__in=to_add)
                    )
                    await pb.aincrease_by(len(to_add))

            if self.allow_delete:
                async with ProgressReport(
                    message="Un-Associating Content", code="unassociating.content"
                ) as pb:
                    if to_delete:
                        await sync_to_async(self.new_version.remove_content)(
                            Content.objects.filter(pk__in=to_delete)
                        )
                        await pb.aincrease_by(len(to_delete))
