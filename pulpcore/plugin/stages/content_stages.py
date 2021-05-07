from collections import defaultdict

from django.core.exceptions import ObjectDoesNotExist
from django.db import DatabaseError, IntegrityError, transaction
from django.db.models import Q

from pulpcore.plugin.models import Content, ContentArtifact, ProgressReport

from .api import Stage


class QueryExistingContents(Stage):
    """
    A Stages API stage that saves :attr:`DeclarativeContent.content` objects and saves its related
    :class:`~pulpcore.plugin.models.ContentArtifact` objects too.

    This stage expects :class:`~pulpcore.plugin.stages.DeclarativeContent` units from `self._in_q`
    and inspects their associated :class:`~pulpcore.plugin.stages.DeclarativeArtifact` objects. Each
    :class:`~pulpcore.plugin.stages.DeclarativeArtifact` object stores one
    :class:`~pulpcore.plugin.models.Artifact`.

    This stage inspects any "unsaved" Content unit objects and searches for existing saved Content
    units inside Pulp with the same unit key. Any existing Content objects found, replace their
    "unsaved" counterpart in the :class:`~pulpcore.plugin.stages.DeclarativeContent` object.

    Each :class:`~pulpcore.plugin.stages.DeclarativeContent` is sent to `self._out_q` after it has
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

            for model_type in content_q_by_type.keys():
                for result in model_type.objects.filter(content_q_by_type[model_type]).iterator():
                    for d_content in d_content_by_nat_key[result.natural_key()]:
                        try:
                            result.touch()
                        except DatabaseError:
                            # update failed so leave content empty to create it later
                            pass
                        else:
                            d_content.content = result

            for d_content in batch:
                await self.put(d_content)


class ContentSaver(Stage):
    """
    A Stages API stage that saves :attr:`DeclarativeContent.content` objects and saves its related
    :class:`~pulpcore.plugin.models.ContentArtifact` objects too.

    This stage expects :class:`~pulpcore.plugin.stages.DeclarativeContent` units from `self._in_q`
    and inspects their associated :class:`~pulpcore.plugin.stages.DeclarativeArtifact` objects. Each
    :class:`~pulpcore.plugin.stages.DeclarativeArtifact` object stores one
    :class:`~pulpcore.plugin.models.Artifact`.

    Each "unsaved" Content objects is saved and a :class:`~pulpcore.plugin.models.ContentArtifact`
    objects too.

    Each :class:`~pulpcore.plugin.stages.DeclarativeContent` is sent to after it has been handled.

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
            content_artifact_bulk = []
            with transaction.atomic():
                await self._pre_save(batch)

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
                            continue
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
                ContentArtifact.objects.bulk_get_or_create(content_artifact_bulk)
                await self._post_save(batch)
            for declarative_content in batch:
                await self.put(declarative_content)

    async def _pre_save(self, batch):
        """
        A hook plugin-writers can override to save related objects prior to content unit saving.

        This is run within the same transaction as the content unit saving.

        Args:
            batch (list of :class:`~pulpcore.plugin.stages.DeclarativeContent`): The batch of
                :class:`~pulpcore.plugin.stages.DeclarativeContent` objects to be saved.

        """
        pass

    async def _post_save(self, batch):
        """
        A hook plugin-writers can override to save related objects after content unit saving.

        This is run within the same transaction as the content unit saving.

        Args:
            batch (list of :class:`~pulpcore.plugin.stages.DeclarativeContent`): The batch of
                :class:`~pulpcore.plugin.stages.DeclarativeContent` objects to be saved.

        """
        pass


class ResolveContentFutures(Stage):
    """
    This stage resolves the futures in :class:`~pulpcore.plugin.stages.DeclarativeContent`.

    Futures results are set to the found/created :class:`~pulpcore.plugin.models.Content`.

    This is useful when data downloaded from the plugin API needs to be parsed by FirstStage to
    create additional :class:`~pulpcore.plugin.stages.DeclarativeContent` objects to be send down
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
    via `self._out_q` to the next stage as a :class:`django.db.models.query.QuerySet`.

    This stage creates a ProgressReport named 'Associating Content' that counts the number of units
    associated. Since it's a stream the total count isn't known until it's finished.

    If `mirror` was enabled, then content units may also be un-assocated (removed) from
    `new_version`. A ProgressReport named 'Un-Associating Content' is created that counts the number
    of units un-associated.

    Args:
        new_version (:class:`~pulpcore.plugin.models.RepositoryVersion`): The repo version this
            stage associates content with.
        mirror (bool): Whether or not to "mirror" the stream of DeclarativeContent - whether content
            not in the stream should be removed from the repository.
        args: unused positional arguments passed along to :class:`~pulpcore.plugin.stages.Stage`.
        kwargs: unused keyword arguments passed along to :class:`~pulpcore.plugin.stages.Stage`.
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
        with ProgressReport(message="Associating Content", code="associating.content") as pb:
            to_delete = set(self.new_version.content.values_list("pk", flat=True))
            async for batch in self.batches():
                to_add = set()
                for d_content in batch:
                    try:
                        to_delete.remove(d_content.content.pk)
                    except KeyError:
                        to_add.add(d_content.content.pk)
                        await self.put(d_content)

                if to_add:
                    self.new_version.add_content(Content.objects.filter(pk__in=to_add))
                    pb.increase_by(len(to_add))

            if self.allow_delete:
                with ProgressReport(
                    message="Un-Associating Content", code="unassociating.content"
                ) as pb:
                    if to_delete:
                        self.new_version.remove_content(Content.objects.filter(pk__in=to_delete))
                        pb.increase_by(len(to_delete))
