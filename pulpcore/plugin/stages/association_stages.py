from django.db.models import Q

from pulpcore.plugin.models import Content, ProgressReport

from .api import Stage


class ContentAssociation(Stage):
    """
    A Stages API stage that associates content units with `new_version`.

    This stage stores all content unit primary keys in memory before running. This is done to
    compute the units already associated but not received from `self._in_q`. These units are passed
    via `self._out_q` to the next stage as a :class:`django.db.models.query.QuerySet`.

    This stage creates a ProgressReport named 'Associating Content' that counts the number of units
    associated. Since it's a stream the total count isn't known until it's finished.

    Args:
        new_version (:class:`~pulpcore.plugin.models.RepositoryVersion`): The repo version this
            stage associates content with.
        args: unused positional arguments passed along to :class:`~pulpcore.plugin.stages.Stage`.
        kwargs: unused keyword arguments passed along to :class:`~pulpcore.plugin.stages.Stage`.
    """

    def __init__(self, new_version, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.new_version = new_version

    async def run(self):
        """
        The coroutine for this stage.

        Returns:
            The coroutine for this stage.
        """
        with ProgressReport(message='Associating Content', code='associating.content') as pb:
            to_delete = set(self.new_version.content.values_list('pk', flat=True))
            async for batch in self.batches():
                to_add = set()
                for d_content in batch:
                    try:
                        to_delete.remove(d_content.content.pk)
                    except KeyError:
                        to_add.add(d_content.content.pk)

                if to_add:
                    self.new_version.add_content(Content.objects.filter(pk__in=to_add))
                    pb.done = pb.done + len(to_add)
                    pb.save()

            if to_delete:
                await self.put(Content.objects.filter(pk__in=to_delete))


class ContentUnassociation(Stage):
    """
    A Stages API stage that unassociates content units from `new_version`.

    This stage creates a ProgressReport named 'Un-Associating Content' that counts the number of
    units un-associated. Since it's a stream the total count isn't known until it's finished.

    Args:
        new_version (:class:`~pulpcore.plugin.models.RepositoryVersion`): The repo version this
            stage unassociates content from.
        args: unused positional arguments passed along to :class:`~pulpcore.plugin.stages.Stage`.
        kwargs: unused keyword arguments passed along to :class:`~pulpcore.plugin.stages.Stage`.
    """

    def __init__(self, new_version, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.new_version = new_version

    async def run(self):
        """
        The coroutine for this stage.

        Returns:
            The coroutine for this stage.
        """
        with ProgressReport(message='Un-Associating Content', code='unassociating.content') as pb:
            async for queryset_to_unassociate in self.items():
                self.new_version.remove_content(queryset_to_unassociate)
                pb.done = pb.done + queryset_to_unassociate.count()
                pb.save()

                await self.put(queryset_to_unassociate)


class RemoveDuplicates(Stage):
    """
    Stage allows plugins to remove content that would break repository uniqueness constraints.

    This stage is expected to be added by the
    :class:`~pulpcore.plugin.stages.DeclarativeVersion`. See that class for example usage.
    """

    def __init__(self, new_version, model, field_names):
        """
        Args:
            new_version (:class:`~pulpcore.plugin.models.RepositoryVersion`): The repo version this
                stage unassociates content from.
            model (:class:`pulpcore.plugin.models.Content`): Subclass of a Content model to
                indicate which content type to operate on.
            field_names (list): List of field names to ensure uniqueness within a repository
                version.
        """
        self.new_version = new_version
        self.model = model
        self.field_names = field_names

    async def run(self):
        """
        The coroutine for this stage.

        Returns:
            The coroutine for this stage.
        """
        async for batch in self.batches():
            rm_q = Q()
            for d_content in batch:
                if isinstance(d_content.content, self.model):
                    unit_q_dict = {
                        field: getattr(d_content.content, field) for field in self.field_names
                    }
                    # Don't remove *this* object if it is already in the repository version.
                    not_this = ~Q(pk=d_content.content.pk)
                    dupe = Q(**unit_q_dict)
                    rm_q |= Q(dupe & not_this)
            if rm_q:
                queryset_to_unassociate = self.model.objects.filter(rm_q)
                self.new_version.remove_content(queryset_to_unassociate)

            for d_content in batch:
                await self.put(d_content)
