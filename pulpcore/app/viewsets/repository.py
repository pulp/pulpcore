import itertools
from gettext import gettext as _

from django_filters import Filter
from django_filters.rest_framework import DjangoFilterBackend, filters
from drf_spectacular.utils import extend_schema
from rest_framework import mixins, serializers
from rest_framework.decorators import action
from rest_framework.filters import OrderingFilter

from pulpcore.app import tasks
from pulpcore.app.models import (
    Content,
    Remote,
    Repository,
    RepositoryContent,
    RepositoryVersion,
)
from pulpcore.app.response import OperationPostponedResponse
from pulpcore.app.serializers import (
    AsyncOperationResponseSerializer,
    RemoteSerializer,
    RepairSerializer,
    RepositorySerializer,
    RepositoryVersionSerializer,
)
from pulpcore.app.viewsets import (
    AsyncRemoveMixin,
    AsyncUpdateMixin,
    BaseFilterSet,
    NamedModelViewSet,
)
from pulpcore.app.viewsets.base import DATETIME_FILTER_OPTIONS, NAME_FILTER_OPTIONS
from pulpcore.app.viewsets.custom_filters import IsoDateTimeFilter
from pulpcore.tasking.tasks import enqueue_with_reservation


class RepositoryFilter(BaseFilterSet):
    name = filters.CharFilter()

    class Meta:
        model = Repository
        fields = {"name": NAME_FILTER_OPTIONS}


class ImmutableRepositoryViewSet(
    NamedModelViewSet,
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.ListModelMixin,
    AsyncRemoveMixin,
):
    """
    An immutable repository ViewSet that does not allow the usage of the methods PATCH and PUT.
    """

    queryset = Repository.objects.all().order_by("name")
    serializer_class = RepositorySerializer
    endpoint_name = "repositories"
    router_lookup = "repository"
    filterset_class = RepositoryFilter


class RepositoryViewSet(ImmutableRepositoryViewSet, AsyncUpdateMixin):
    """
    A ViewSet for an ordinary repository.
    """


class RepositoryVersionContentFilter(Filter):
    """
    Filter used to get the repository versions where some given content can be found.

    Given a content_href, this filter will:
        1. Get the RepositoryContent that the content can be found in
        2. Get a list of version_added and version_removed where the content was
           changed on the repository
        3. Calculate and return the versions that the content can be found on
    """

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("help_text", _("Content Unit referenced by HREF"))
        super().__init__(*args, **kwargs)

    def filter(self, qs, value):
        """
        Args:
            qs (django.db.models.query.QuerySet): The RepositoryVersion Queryset
            value (string): of content href to filter

        Returns:
            Queryset of the RepositoryVersions containing the specified content
        """

        if value is None:
            # user didn't supply a value
            return qs

        if not value:
            raise serializers.ValidationError(detail=_("No value supplied for content filter"))

        # Get the content object from the content_href
        content = NamedModelViewSet.get_resource(value, Content)

        # Get the repository from the parent request.
        repository_pk = self.parent.request.parser_context["kwargs"]["repository_pk"]
        repository = Repository.objects.get(pk=repository_pk)

        repository_content_set = RepositoryContent.objects.filter(
            content=content, repository=repository
        )

        # Get the sorted list of version_added and version_removed.
        version_added = list(repository_content_set.values_list("version_added__number", flat=True))

        # None values have to be filtered out from version_removed,
        # in order for zip_longest to pass it a default fillvalue
        version_removed = list(
            filter(
                None.__ne__,
                repository_content_set.values_list("version_removed__number", flat=True),
            )
        )

        # The range finding should work as long as both lists are sorted
        # Why it works: https://gist.github.com/werwty/6867f83ae5adbae71e452c28ecd9c444
        version_added.sort()
        version_removed.sort()

        # Match every version_added to a version_removed, if len(version_removed)
        # is shorter than len(version_added), pad out the remaining space with the current
        # repository version +1 (the +1 is to the current version gets included when we
        # calculate range)
        version_tuples = itertools.zip_longest(
            version_added, version_removed, fillvalue=repository.next_version
        )

        # Get the ranges between paired version_added and version_removed to get all
        # the versions the content is present in.
        versions = [list(range(added, removed)) for (added, removed) in version_tuples]
        # Flatten the list of lists
        versions = list(itertools.chain.from_iterable(versions))

        return qs.filter(number__in=versions)


class RepositoryVersionFilter(BaseFilterSet):
    # e.g.
    # /?number=4
    # /?number__range=4,6
    # /?pulp_created__gte=2018-04-12T19:45
    # /?pulp_created__range=2018-04-12T19:45,2018-04-13T20:00
    # /?content=/pulp/api/v3/content/file/fb8ad2d0-03a8-4e36-a209-77763d4ed16c/
    number = filters.NumberFilter()
    pulp_created = IsoDateTimeFilter()
    content = RepositoryVersionContentFilter()
    content__in = RepositoryVersionContentFilter(field_name="content", lookup_expr="in")

    class Meta:
        model = RepositoryVersion
        fields = {
            "number": ["exact", "lt", "lte", "gt", "gte", "range"],
            "pulp_created": DATETIME_FILTER_OPTIONS,
        }


class RepositoryVersionViewSet(
    NamedModelViewSet, mixins.RetrieveModelMixin, mixins.ListModelMixin, mixins.DestroyModelMixin
):
    endpoint_name = "versions"
    nest_prefix = "repositories"
    router_lookup = "version"
    lookup_field = "number"
    parent_viewset = RepositoryViewSet
    parent_lookup_kwargs = {"repository_pk": "repository__pk"}
    serializer_class = RepositoryVersionSerializer
    queryset = RepositoryVersion.objects.exclude(complete=False)
    filterset_class = RepositoryVersionFilter
    filter_backends = (OrderingFilter, DjangoFilterBackend)
    ordering = ("-number",)

    @extend_schema(
        description="Trigger an asynchronous task to delete a repository version.",
        responses={202: AsyncOperationResponseSerializer},
    )
    def destroy(self, request, repository_pk, number):
        """
        Queues a task to handle deletion of a RepositoryVersion
        """
        version = self.get_object()

        if version.number == 0:
            raise serializers.ValidationError(detail=_("Cannot delete repository version 0."))

        async_result = enqueue_with_reservation(
            tasks.repository.delete_version, [version.repository], kwargs={"pk": version.pk}
        )
        return OperationPostponedResponse(async_result, request)

    @extend_schema(
        description="Trigger an asynchronous task to repair a repository version.",
        responses={202: AsyncOperationResponseSerializer},
    )
    @action(detail=True, methods=["post"])
    def repair(self, request, repository_pk, number):
        """
        Queues a task to repair corrupted artifacts corresponding to a RepositoryVersion
        """
        version = self.get_object()
        serializer = RepairSerializer(data=request.data)
        serializer.is_valid()

        verify_checksums = serializer.validated_data["verify_checksums"]

        async_result = enqueue_with_reservation(
            tasks.repository.repair_version,
            [version.repository],
            args=[version.pk, verify_checksums],
        )
        return OperationPostponedResponse(async_result, request)


class RemoteFilter(BaseFilterSet):
    """
    Plugin remote filter should:
     - inherit from this class
     - add any specific filters if needed
     - define a `Meta` class which should:
       - specify a plugin remote model for which filter is defined
       - extend `fields` with specific ones
    """

    name = filters.CharFilter()
    pulp_last_updated = IsoDateTimeFilter()

    class Meta:
        model = Remote
        fields = {"name": NAME_FILTER_OPTIONS, "pulp_last_updated": DATETIME_FILTER_OPTIONS}


class RemoteViewSet(
    NamedModelViewSet,
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.ListModelMixin,
    AsyncUpdateMixin,
    AsyncRemoveMixin,
):
    endpoint_name = "remotes"
    serializer_class = RemoteSerializer
    queryset = Remote.objects.all()
    filterset_class = RemoteFilter
