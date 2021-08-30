from gettext import gettext as _

from django.shortcuts import get_object_or_404
from django_filters import Filter
from django_filters.rest_framework import DjangoFilterBackend, filters
from drf_spectacular.utils import extend_schema
from rest_framework import mixins, serializers
from rest_framework.filters import OrderingFilter
from rest_framework.decorators import action
from rest_framework.response import Response

from pulpcore.app.models import (
    ContentGuard,
    RBACContentGuard,
    Distribution,
    Publication,
    Content,
)
from pulpcore.app.serializers import (
    ContentGuardSerializer,
    DistributionSerializer,
    PublicationSerializer,
    RBACContentGuardSerializer,
    RBACContentGuardPermissionSerializer,
)
from pulpcore.app.viewsets import (
    AsyncCreateMixin,
    AsyncRemoveMixin,
    AsyncUpdateMixin,
    BaseFilterSet,
    NamedModelViewSet,
)
from pulpcore.app.viewsets.base import DATETIME_FILTER_OPTIONS, NAME_FILTER_OPTIONS
from pulpcore.app.viewsets.custom_filters import (
    IsoDateTimeFilter,
    LabelSelectFilter,
    RepositoryVersionFilter,
)


class PublicationContentFilter(Filter):
    def __init__(self, *args, **kwargs):
        kwargs.setdefault("help_text", _("Content Unit referenced by HREF"))
        super().__init__(*args, **kwargs)

    def filter(self, qs, value):
        if value is None:
            # user didn't supply a value
            return qs

        if not value:
            raise serializers.ValidationError(detail=_("No value supplied for content filter"))

        # Get the content object from the content_href
        content = NamedModelViewSet.get_resource(value, Content)

        return qs.with_content([content.pk])


class PublicationFilter(BaseFilterSet):
    repository_version = RepositoryVersionFilter()
    pulp_created = IsoDateTimeFilter()
    content = PublicationContentFilter()
    content__in = PublicationContentFilter(field_name="content", lookup_expr="in")

    class Meta:
        model = Publication
        fields = {
            "repository_version": ["exact"],
            "pulp_created": DATETIME_FILTER_OPTIONS,
        }


class ListPublicationViewSet(NamedModelViewSet, mixins.ListModelMixin):
    endpoint_name = "publications"
    queryset = Publication.objects.all()
    serializer_class = PublicationSerializer
    filterset_class = PublicationFilter

    @classmethod
    def is_master_viewset(cls):
        """Do not hide from the routers."""
        return False


class PublicationViewSet(
    NamedModelViewSet, mixins.RetrieveModelMixin, mixins.ListModelMixin, mixins.DestroyModelMixin
):
    endpoint_name = "publications"
    queryset = Publication.objects.exclude(complete=False)
    serializer_class = PublicationSerializer
    filter_backends = (OrderingFilter, DjangoFilterBackend)
    filterset_class = PublicationFilter
    ordering = ("-pulp_created",)


class ContentGuardFilter(BaseFilterSet):
    name = filters.CharFilter()

    class Meta:
        model = ContentGuard
        fields = {
            "name": NAME_FILTER_OPTIONS,
        }


class BaseContentGuardViewSet(NamedModelViewSet):
    endpoint_name = "contentguards"
    serializer_class = ContentGuardSerializer
    queryset = ContentGuard.objects.all()
    filterset_class = ContentGuardFilter


class ListContentGuardViewSet(
    BaseContentGuardViewSet,
    mixins.ListModelMixin,
):
    """Endpoint to list all contentguards."""

    @classmethod
    def is_master_viewset(cls):
        """Do not hide from the routers."""
        return False


class ContentGuardViewSet(
    BaseContentGuardViewSet,
    mixins.CreateModelMixin,
    mixins.UpdateModelMixin,
    mixins.DestroyModelMixin,
    mixins.RetrieveModelMixin,
    mixins.ListModelMixin,
):
    """
    A viewset for contentguards.
    """


class RBACContentGuardViewSet(ContentGuardViewSet):
    """
    Viewset for creating contentguards that use RBAC to protect content.
    Has add and remove actions for managing permission for users and groups to download content
    protected by this guard.
    """

    endpoint_name = "rbac"
    serializer_class = RBACContentGuardSerializer
    queryset = RBACContentGuard.objects.all()

    DEFAULT_ACCESS_POLICY = {
        "statements": [
            {
                "action": ["list"],
                "principal": "authenticated",
                "effect": "allow",
            },
            {
                "action": ["create"],
                "principal": "authenticated",
                "effect": "allow",
                "condition": "has_model_perms:core.add_rbaccontentguard",
            },
            {
                "action": ["retrieve"],
                "principal": "authenticated",
                "effect": "allow",
                "condition": "has_model_or_obj_perms:core.view_rbaccontentguard",
            },
            {
                "action": ["update", "partial_update", "assign_permission", "remove_permission"],
                "principal": "authenticated",
                "effect": "allow",
                "condition": "has_model_or_obj_perms:core.change_rbaccontentguard",
            },
            {
                "action": ["destroy"],
                "principal": "authenticated",
                "effect": "allow",
                "condition": "has_model_or_obj_perms:core.delete_rbaccontentguard",
            },
            {
                "action": ["download"],  # This is the action for the content guard permit
                "principal": "authenticated",
                "effect": "allow",
                "condition": "has_model_or_obj_perms:core.download_rbaccontentguard",
            },
        ],
        "permissions_assignment": [
            {
                "function": "add_for_object_creator",
                "parameters": None,
                "permissions": [
                    "core.add_rbaccontentguard",
                    "core.view_rbaccontentguard",
                    "core.change_rbaccontentguard",
                    "core.delete_rbaccontentguard",
                    "core.download_rbaccontentguard",
                ],
            },
        ],
    }

    @extend_schema(summary="Add download permission", responses={201: RBACContentGuardSerializer})
    @action(methods=["post"], detail=True, serializer_class=RBACContentGuardPermissionSerializer)
    def assign_permission(self, request, pk):
        """Give users and groups the `download` permission"""
        guard = get_object_or_404(RBACContentGuard, pk=pk)
        names = self.get_serializer(data=request.data)
        names.is_valid(raise_exception=True)
        guard.add_can_download(users=names.data["usernames"], groups=names.data["groupnames"])
        self.serializer_class = RBACContentGuardSerializer
        serializer = self.get_serializer(guard)
        return Response(serializer.data, status=201)

    @extend_schema(
        summary="Remove download permission", responses={201: RBACContentGuardSerializer}
    )
    @action(methods=["post"], detail=True, serializer_class=RBACContentGuardPermissionSerializer)
    def remove_permission(self, request, pk):
        """Remove `download` permission from users and groups"""
        guard = get_object_or_404(RBACContentGuard, pk=pk)
        names = self.get_serializer(data=request.data)
        names.is_valid(raise_exception=True)
        guard.remove_can_download(users=names.data["usernames"], groups=names.data["groupnames"])
        self.serializer_class = RBACContentGuardSerializer
        serializer = self.get_serializer(guard)
        return Response(serializer.data, status=201)


class DistributionFilter(BaseFilterSet):
    # e.g.
    # /?name=foo
    # /?name__in=foo,bar
    # /?base_path__contains=foo
    # /?base_path__icontains=foo
    name = filters.CharFilter()
    base_path = filters.CharFilter()
    pulp_label_select = LabelSelectFilter()

    class Meta:
        model = Distribution
        fields = {
            "name": NAME_FILTER_OPTIONS,
            "base_path": ["exact", "contains", "icontains", "in"],
        }


class DistributionViewSet(
    NamedModelViewSet,
    mixins.RetrieveModelMixin,
    mixins.ListModelMixin,
    AsyncCreateMixin,
    AsyncRemoveMixin,
    AsyncUpdateMixin,
):
    """
    Provides read and list methods and also provides asynchronous CUD methods to dispatch tasks
    with reservation that lock all Distributions preventing race conditions during base_path
    checking.
    """

    endpoint_name = "distributions"
    queryset = Distribution.objects.all()
    serializer_class = DistributionSerializer
    filterset_class = DistributionFilter

    def async_reserved_resources(self, instance):
        """Return resource that locks all Distributions."""
        return ["/api/v3/distributions/"]
