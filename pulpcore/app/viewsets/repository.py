from gettext import gettext as _

from collections import defaultdict
from django.db.models import Q, Max
from django.urls.base import Resolver404, resolve
from django_filters import Filter
from drf_spectacular.utils import extend_schema
from rest_framework import mixins, serializers
from rest_framework.decorators import action
from rest_framework.viewsets import GenericViewSet
from urllib.parse import urlparse

from pulpcore.constants import PROTECTED_REPO_VERSION_MESSAGE
from pulpcore.filters import BaseFilterSet
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
    LabelsMixin,
    NamedModelViewSet,
)
from pulpcore.app.viewsets.base import (
    DATETIME_FILTER_OPTIONS,
    NAME_FILTER_OPTIONS,
    NULLABLE_NUMERIC_FILTER_OPTIONS,
)
from pulpcore.app.viewsets.custom_filters import LabelFilter
from pulpcore.tasking.tasks import dispatch
from pulpcore.filters import HyperlinkRelatedFilter


class RepositoryContentFilter(Filter):
    """
    Filter used to filter repositories which have a piece of content
    """

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("help_text", _("Content Unit referenced by HREF"))
        self.latest = kwargs.pop("latest", False)
        super().__init__(*args, **kwargs)

    def filter(self, qs, value):
        """
        Args:
            qs (django.db.models.query.QuerySet): The Repository Queryset
            value (string): of content href to filter

        Returns:
            Queryset of the Repository containing the specified content
        """

        if value is None:
            # user didn't supply a value
            return qs

        if not value:
            raise serializers.ValidationError(detail=_("No value supplied for content filter"))

        # Get the content object from the content_href
        content = NamedModelViewSet.get_resource(value, Content)

        if self.latest:
            return qs.filter(
                pk__in=RepositoryContent.objects.filter(
                    version_removed=None, content__pk=content.pk
                ).values_list("repository__pk", flat=True)
            )
        else:
            return qs.filter(content__pk=content.pk)


class RepositoryFilter(BaseFilterSet):
    pulp_label_select = LabelFilter()
    remote = HyperlinkRelatedFilter(allow_null=True)
    with_content = RepositoryContentFilter()
    latest_with_content = RepositoryContentFilter(latest=True)

    class Meta:
        model = Repository
        fields = {
            "name": NAME_FILTER_OPTIONS,
            "retain_repo_versions": NULLABLE_NUMERIC_FILTER_OPTIONS,
        }


class BaseRepositoryViewSet(NamedModelViewSet):
    """
    A base class for any repository viewset.
    """

    queryset = Repository.objects.exclude(user_hidden=True).order_by("name")
    serializer_class = RepositorySerializer
    endpoint_name = "repositories"
    router_lookup = "repository"
    filterset_class = RepositoryFilter

    def get_queryset(self):
        """Apply optimizations for list endpoint."""
        qs = super().get_queryset()
        if getattr(self, "action", "") == "list":
            # Fetch info for remote (DetailRelatedField) and latest_version (LatestVersionField)
            qs = (
                qs.select_related("remote")
                .only(*self.queryset.model.get_field_names(), "remote__pulp_type")
                .annotate(
                    latest_version_number=Max("versions__number", filter=Q(versions__complete=True))
                )
            )
        return qs


class ListRepositoryViewSet(BaseRepositoryViewSet, mixins.ListModelMixin):
    """Endpoint to list all repositories."""

    DEFAULT_ACCESS_POLICY = {
        "statements": [
            {
                "action": ["list"],
                "principal": "authenticated",
                "effect": "allow",
            },
        ],
        "queryset_scoping": {"function": "scope_queryset"},
    }

    @classmethod
    def routable(cls):
        """Do not hide from the routers."""
        return True


class ReadOnlyRepositoryViewSet(
    BaseRepositoryViewSet,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
):
    """
    A readonly repository which allows only GET method.
    """

    queryset = Repository.objects.all().order_by("name")
    serializer_class = RepositorySerializer
    endpoint_name = "repositories"
    router_lookup = "repository"
    filterset_class = RepositoryFilter


class ImmutableRepositoryViewSet(
    ReadOnlyRepositoryViewSet,
    mixins.CreateModelMixin,
    AsyncRemoveMixin,
):
    # Too many cascaded deletes to block the gunicorn worker.
    ALLOW_NON_BLOCKING_DELETE = False

    """
    An immutable repository ViewSet that does not allow the usage of the methods PATCH and PUT.
    """


class RepositoryViewSet(ImmutableRepositoryViewSet, AsyncUpdateMixin, LabelsMixin):
    """
    A ViewSet for an ordinary repository.
    """


class RepositoryVersionContentFilter(Filter):
    """
    Filter used to get the repository versions where some given content can be found.
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

        return qs.with_content([content.pk])


class RepositoryVersionFilter(BaseFilterSet):
    # e.g.
    # /?number=4
    # /?number__range=4,6
    # /?pulp_created__gte=2018-04-12T19:45
    # /?pulp_created__range=2018-04-12T19:45,2018-04-13T20:00
    # /?content=/pulp/api/v3/content/file/fb8ad2d0-03a8-4e36-a209-77763d4ed16c/
    content = RepositoryVersionContentFilter()
    content__in = RepositoryVersionContentFilter(field_name="content", lookup_expr="in")

    def filter_pulp_href(self, queryset, name, value):
        """Special handling for RepositoryVersion HREF filtering."""
        repo_versions = defaultdict(list)
        for uri in value:
            try:
                href_match = resolve(urlparse(uri).path).kwargs
            except Resolver404:
                href_match = {}
            if "repository_pk" not in href_match or "number" not in href_match:
                raise serializers.ValidationError(
                    _("Invalid RepositoryVersion HREF: {}".format(uri))
                )
            repo_versions[href_match["repository_pk"]].append(int(href_match["number"]))

        filter_Q = Q()
        for repo_pk, numbers in repo_versions.items():
            filter_Q |= Q(repository__pk=repo_pk, number__in=numbers)
        return queryset.filter(filter_Q)

    class Meta:
        model = RepositoryVersion
        fields = {
            "number": ["exact", "lt", "lte", "gt", "gte", "range"],
            "pulp_created": DATETIME_FILTER_OPTIONS,
        }
        exclude = ["pulp_id__in"]


class RepositoryVersionQuerysetMixin:
    """A mixin to hold the shared get_queryset logic used by RepositoryVersionViewSets."""

    def get_queryset(self):
        qs = super().get_queryset()
        if getattr(self, "action", "") == "list":
            # Fetch info for repository (DetailRelatedField),
            # base_version (RepositoryVersionRelatedField), and
            # counts (ContentSummarySerializer)
            qs = (
                qs.select_related("repository", "base_version__repository")
                .only(
                    *self.queryset.model.get_field_names(),
                    "repository__pulp_type",
                )
                .prefetch_related("counts")
            )
        return qs


class RepositoryVersionViewSet(
    RepositoryVersionQuerysetMixin,
    NamedModelViewSet,
    mixins.RetrieveModelMixin,
    mixins.ListModelMixin,
    mixins.DestroyModelMixin,
):
    endpoint_name = "versions"
    nest_prefix = "repositories"
    router_lookup = "version"
    lookup_field = "number"
    parent_viewset = RepositoryViewSet
    parent_lookup_kwargs = {"repository_pk": "repository__pk"}
    serializer_class = RepositoryVersionSerializer
    queryset = RepositoryVersion.objects.complete()
    filterset_class = RepositoryVersionFilter
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

        if version in version.repository.protected_versions():
            raise serializers.ValidationError(PROTECTED_REPO_VERSION_MESSAGE)

        task = dispatch(
            tasks.repository.delete_version,
            exclusive_resources=[version.repository],
            kwargs={"pk": version.pk},
        )
        return OperationPostponedResponse(task, request)

    @extend_schema(
        description="Trigger an asynchronous task to repair a repository version.",
        responses={202: AsyncOperationResponseSerializer},
    )
    @action(detail=True, methods=["post"], serializer_class=RepairSerializer)
    def repair(self, request, repository_pk, number):
        """
        Queues a task to repair corrupted artifacts corresponding to a RepositoryVersion
        """
        version = self.get_object()
        serializer = RepairSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        verify_checksums = serializer.validated_data["verify_checksums"]

        task = dispatch(
            tasks.repository.repair_version,
            shared_resources=[version.repository],
            args=[version.pk, verify_checksums],
        )
        return OperationPostponedResponse(task, request)


class RemoteFilter(BaseFilterSet):
    """
    Plugin remote filter should:
     - inherit from this class
     - add any specific filters if needed
     - define a `Meta` class which should:
       - specify a plugin remote model for which filter is defined
       - extend `fields` with specific ones
    """

    pulp_label_select = LabelFilter()

    class Meta:
        model = Remote
        fields = {"name": NAME_FILTER_OPTIONS, "pulp_last_updated": DATETIME_FILTER_OPTIONS}


class ListRemoteViewSet(NamedModelViewSet, mixins.ListModelMixin):
    endpoint_name = "remotes"
    queryset = Remote.objects.all()
    serializer_class = RemoteSerializer
    filterset_class = RemoteFilter

    DEFAULT_ACCESS_POLICY = {
        "statements": [
            {
                "action": ["list"],
                "principal": "authenticated",
                "effect": "allow",
            },
        ],
        "queryset_scoping": {"function": "scope_queryset"},
    }

    @classmethod
    def routable(cls):
        """Do not hide from the routers."""
        return True


class RemoteViewSet(
    NamedModelViewSet,
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.ListModelMixin,
    AsyncUpdateMixin,
    AsyncRemoveMixin,
    LabelsMixin,
):
    # Too many cascaded deletes to block the gunicorn worker.
    ALLOW_NON_BLOCKING_DELETE = False

    endpoint_name = "remotes"
    serializer_class = RemoteSerializer
    queryset = Remote.objects.all()
    filterset_class = RemoteFilter


# We have to use GenericViewSet as NamedModelViewSet causes
# get_viewset_for_model() to match multiple viewsets.
class ListRepositoryVersionViewSet(
    RepositoryVersionQuerysetMixin,
    GenericViewSet,
    mixins.ListModelMixin,
):
    endpoint_name = "repository_versions"
    serializer_class = RepositoryVersionSerializer
    queryset = RepositoryVersion.objects.exclude(repository__user_hidden=True)
    filterset_class = RepositoryVersionFilter

    DEFAULT_ACCESS_POLICY = {
        "statements": [
            {
                "action": ["list"],
                "principal": "authenticated",
                "effect": "allow",
            },
        ],
        "queryset_scoping": {"function": "scope_queryset"},
    }

    def scope_queryset(self, qs):
        """This scopes based on repositories the user can see (similar to content)."""
        if not self.request.user.is_superuser:
            repo_viewset = ListRepositoryViewSet()
            setattr(repo_viewset, "request", self.request)
            repos = repo_viewset.get_queryset()
            qs = qs.filter(repository__in=repos)
        return qs
