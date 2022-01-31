from gettext import gettext as _

from django_filters import Filter
from django_filters.rest_framework import DjangoFilterBackend, filters
from rest_framework import mixins, serializers
from rest_framework.filters import OrderingFilter

from pulpcore.app.models import (
    ContentGuard,
    RBACContentGuard,
    ContentRedirectContentGuard,
    Distribution,
    Publication,
    Content,
)
from pulpcore.app.serializers import (
    ContentGuardSerializer,
    DistributionSerializer,
    PublicationSerializer,
    RBACContentGuardSerializer,
    ContentRedirectContentGuardSerializer,
)
from pulpcore.app.viewsets import (
    AsyncCreateMixin,
    AsyncRemoveMixin,
    AsyncUpdateMixin,
    BaseFilterSet,
    NamedModelViewSet,
    RolesMixin,
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


class RBACContentGuardViewSet(ContentGuardViewSet, RolesMixin):
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
                "action": ["retrieve", "my_permissions"],
                "principal": "authenticated",
                "effect": "allow",
                "condition": "has_model_or_obj_perms:core.view_rbaccontentguard",
            },
            {
                "action": ["update", "partial_update"],
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
            {
                "action": ["list_roles", "add_role", "remove_role"],
                "principal": "authenticated",
                "effect": "allow",
                "condition": "has_model_or_obj_perms:core.manage_roles_rbaccontentguard",
            },
        ],
        "creation_hooks": [
            {
                "function": "add_roles_for_object_creator",
                "parameters": {
                    "roles": ["core.rbaccontentguard_owner", "core.rbaccontentguard_downloader"]
                },
            },
        ],
    }
    LOCKED_ROLES = {
        "core.rbaccontentguard_creator": ["core.add_rbaccontentguard"],
        "core.rbaccontentguard_owner": [
            "core.view_rbaccontentguard",
            "core.change_rbaccontentguard",
            "core.delete_rbaccontentguard",
            "core.manage_roles_rbaccontentguard",
        ],
        "core.rbaccontentguard_downloader": ["core.download_rbaccontentguard"],
    }


class ContentRedirectContentGuardViewSet(ContentGuardViewSet):
    """
    Content guard to protect preauthenticated redirects to the content app.
    """

    endpoint_name = "content_redirect"
    queryset = ContentRedirectContentGuard.objects.all()
    serializer_class = ContentRedirectContentGuardSerializer


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
