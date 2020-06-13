from collections import defaultdict
from itertools import chain

from django.db import IntegrityError, transaction

from pulpcore.plugin.models import ContentArtifact

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
            key_attribute_by_type = {}
            key_attribute_values_by_type = defaultdict(set)
            unsaved_content = []
            deduplicated_content = []

            for d_content in batch:
                if d_content.content._state.adding:
                    # Content that has not yet been saved could potentially a duplicate already in
                    # the database, build up a query to search for such duplicates.
                    unsaved_content.append(d_content)
                    model_type = type(d_content.content)

                    # This could produce false positive duplicates because it matches only on a
                    # single attribute of the content -- but we handle this when processing the
                    # results of this query.
                    try:
                        key_attribute = key_attribute_by_type[model_type]
                    except KeyError:
                        key_attribute = model_type.natural_key_fields()[0]
                        key_attribute_by_type[model_type] = key_attribute

                    key_attribute_values_by_type[model_type].add(
                        getattr(d_content.content, key_attribute)
                    )

                else:
                    # Content that is already saved is already unique / deduplicated, no further
                    # processing needed.
                    deduplicated_content.append(d_content)

            for model_type, key_attr_values in key_attribute_values_by_type.items():
                # Store the declarative content objects in a dictionary using their natural key as
                # the key. For each existing content found in the database, compute the full
                # natural key and look up the natural key in the dictionary. If a match is found,
                # for each declarative content we swap out its content with the already-saved one,
                # and remove the entry from the dictionary to speed up future lookups.
                dc_by_natural_key = defaultdict(list)

                for dc in unsaved_content:
                    if type(dc.content) is model_type:
                        dc_by_natural_key[dc.content.natural_key()].append(dc)

                attr_param = "{attr}__in".format(attr=key_attribute_by_type[model_type])
                query_params = {attr_param: key_attr_values}

                for result in (
                    model_type.objects.filter(**query_params)
                    .only(*model_type.natural_key_fields())
                    .iterator()
                ):
                    result_key = result.natural_key()
                    try:
                        d_content_list = dc_by_natural_key[result_key]
                        for d_content_item in d_content_list:
                            d_content_item.content = result
                            deduplicated_content.append(d_content_item)
                        del dc_by_natural_key[result_key]
                    except KeyError:
                        pass

                deduplicated_content.extend(chain.from_iterable(dc_by_natural_key.values()))

            content_in = len(batch)
            content_out = len(deduplicated_content)
            assert (
                content_in == content_out
            ), f"content in ({content_in}) != content out ({content_out})"

            for d_content in deduplicated_content:
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
                        except IntegrityError:
                            d_content.content = d_content.content.__class__.objects.get(
                                d_content.content.q()
                            )
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
