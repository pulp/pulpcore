from gettext import gettext as _

from django.db.models import Prefetch
from django_filters import Filter
from rest_framework import mixins, serializers

from pulpcore.app.models.publication import CompositeContentGuard
from pulpcore.app.serializers.publication import CompositeContentGuardSerializer
from pulpcore.filters import BaseFilterSet
from pulpcore.app.models import (
    ContentGuard,
    RBACContentGuard,
    ContentRedirectContentGuard,
    HeaderContentGuard,
    Distribution,
    Publication,
    Repository,
    Content,
    ArtifactDistribution,
)
from pulpcore.app.serializers import (
    ContentGuardSerializer,
    DistributionSerializer,
    PublicationSerializer,
    RBACContentGuardSerializer,
    ContentRedirectContentGuardSerializer,
    HeaderContentGuardSerializer,
    ArtifactDistributionSerializer,
)
from pulpcore.app.viewsets import (
    AsyncCreateMixin,
    AsyncRemoveMixin,
    AsyncUpdateMixin,
    LabelsMixin,
    NamedModelViewSet,
    RolesMixin,
)
from pulpcore.app.viewsets.base import DATETIME_FILTER_OPTIONS, NAME_FILTER_OPTIONS
from pulpcore.app.viewsets.custom_filters import (
    DistributionWithContentFilter,
    LabelFilter,
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


class RepositoryThroughVersionFilter(Filter):
    def filter(self, qs, value):
        if value is None:
            # user didn't supply a value
            return qs

        if not value:
            raise serializers.ValidationError(
                detail=_("No value supplied for {name} filter").format(name=self.field_name)
            )

        repository = NamedModelViewSet.get_resource(value, Repository)
        return qs.filter(repository_version__repository=repository)


class PublicationFilter(BaseFilterSet):
    repository = RepositoryThroughVersionFilter(help_text=_("Repository referenced by HREF"))
    repository_version = RepositoryVersionFilter()
    content = PublicationContentFilter()
    content__in = PublicationContentFilter(field_name="content", lookup_expr="in")

    class Meta:
        model = Publication
        fields = {
            "pulp_created": DATETIME_FILTER_OPTIONS,
        }


class BasePublicationViewSet(NamedModelViewSet):
    """
    A base class for any publication viewset.
    """

    endpoint_name = "publications"
    queryset = Publication.objects.filter(complete=True)
    serializer_class = PublicationSerializer
    filterset_class = PublicationFilter
    ordering = ("-pulp_created",)

    def get_queryset(self):
        """Apply optimizations for list endpoint."""
        qs = super().get_queryset()
        if getattr(self, "action", "") == "list":
            # Fetch info for repository (DetailRelatedField),
            # repository_version (RepositoryVersionRelatedField), and
            # distributions (DetailRelatedField(many=True)) (found on plugin serializers)
            qs = (
                qs.select_related("repository_version__repository")
                .only(
                    *self.queryset.model.get_field_names(),
                    "repository_version__number",
                    "repository_version__repository__pulp_type",
                )
                .prefetch_related(
                    Prefetch(
                        "distribution_set",
                        queryset=Distribution.objects.only("pulp_type", "publication"),
                    ),
                )
            )
        return qs


class ListPublicationViewSet(BasePublicationViewSet, mixins.ListModelMixin):
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


class PublicationViewSet(
    BasePublicationViewSet,
    mixins.RetrieveModelMixin,
    mixins.ListModelMixin,
    mixins.DestroyModelMixin,
):
    """
    Provides read, list and destroy methods for publications. Plugins should inherit from this.
    """


class ContentGuardFilter(BaseFilterSet):
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
    queryset_filtering_required_permission = "core.view_rbaccontentguard"

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
                "condition": "has_model_or_domain_perms:core.add_rbaccontentguard",
            },
            {
                "action": ["retrieve", "my_permissions"],
                "principal": "authenticated",
                "effect": "allow",
                "condition": "has_model_or_domain_or_obj_perms:core.view_rbaccontentguard",
            },
            {
                "action": ["update", "partial_update"],
                "principal": "authenticated",
                "effect": "allow",
                "condition": "has_model_or_domain_or_obj_perms:core.change_rbaccontentguard",
            },
            {
                "action": ["destroy"],
                "principal": "authenticated",
                "effect": "allow",
                "condition": "has_model_or_domain_or_obj_perms:core.delete_rbaccontentguard",
            },
            {
                "action": ["download"],  # This is the action for the content guard permit
                "principal": "authenticated",
                "effect": "allow",
                "condition": "has_model_or_domain_or_obj_perms:core.download_rbaccontentguard",
            },
            {
                "action": ["list_roles", "add_role", "remove_role"],
                "principal": "authenticated",
                "effect": "allow",
                "condition": "has_model_or_domain_or_obj_perms:core.manage_roles_rbaccontentguard",
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
        "queryset_scoping": {"function": "scope_queryset"},
    }
    LOCKED_ROLES = {
        "core.rbaccontentguard_creator": ["core.add_rbaccontentguard"],
        "core.rbaccontentguard_owner": [
            "core.view_rbaccontentguard",
            "core.change_rbaccontentguard",
            "core.delete_rbaccontentguard",
            "core.manage_roles_rbaccontentguard",
        ],
        "core.rbaccontentguard_viewer": ["core.view_rbaccontentguard"],
        "core.rbaccontentguard_downloader": ["core.download_rbaccontentguard"],
    }


class ContentRedirectContentGuardViewSet(ContentGuardViewSet, RolesMixin):
    """
    Content guard to protect preauthenticated redirects to the content app.
    """

    endpoint_name = "content_redirect"
    queryset = ContentRedirectContentGuard.objects.all()
    serializer_class = ContentRedirectContentGuardSerializer
    queryset_filtering_required_permission = "core.view_contentredirectcontentguard"

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
                "condition": "has_model_or_domain_perms:core.add_contentredirectcontentguard",
            },
            {
                "action": ["retrieve", "my_permissions"],
                "principal": "authenticated",
                "effect": "allow",
                "condition": "has_model_or_domain_or_obj_perms:core."
                "view_contentredirectcontentguard",
            },
            {
                "action": ["update", "partial_update"],
                "principal": "authenticated",
                "effect": "allow",
                "condition": (
                    "has_model_or_domain_or_obj_perms:core.change_contentredirectcontentguard"
                ),
            },
            {
                "action": ["destroy"],
                "principal": "authenticated",
                "effect": "allow",
                "condition": (
                    "has_model_or_domain_or_obj_perms:core.delete_contentredirectcontentguard"
                ),
            },
            {
                "action": ["list_roles", "add_role", "remove_role"],
                "principal": "authenticated",
                "effect": "allow",
                "condition": (
                    "has_model_or_domain_or_obj_perms:core.manage_roles_contentredirectcontentguard"
                ),
            },
        ],
        "creation_hooks": [
            {
                "function": "add_roles_for_object_creator",
                "parameters": {"roles": ["core.contentredirectcontentguard_owner"]},
            },
        ],
        "queryset_scoping": {"function": "scope_queryset"},
    }
    LOCKED_ROLES = {
        "core.contentredirectcontentguard_creator": ["core.add_contentredirectcontentguard"],
        "core.contentredirectcontentguard_owner": [
            "core.view_contentredirectcontentguard",
            "core.change_contentredirectcontentguard",
            "core.delete_contentredirectcontentguard",
            "core.manage_roles_contentredirectcontentguard",
        ],
        "core.contentredirectcontentguard_viewer": ["core.view_contentredirectcontentguard"],
    }


class HeaderContentGuardViewSet(ContentGuardViewSet, RolesMixin):
    """
    Content guard to protect the content app using a specific header.
    """

    endpoint_name = "header"
    queryset = HeaderContentGuard.objects.all()
    serializer_class = HeaderContentGuardSerializer
    queryset_filtering_required_permission = "core.view_headercontentguard"

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
                "condition": "has_model_or_domain_perms:core.add_headercontentguard",
            },
            {
                "action": ["retrieve", "my_permissions"],
                "principal": "authenticated",
                "effect": "allow",
                "condition": "has_model_or_domain_or_obj_perms:core.view_headercontentguard",
            },
            {
                "action": ["update", "partial_update"],
                "principal": "authenticated",
                "effect": "allow",
                "condition": ("has_model_or_domain_or_obj_perms:core.change_headercontentguard"),
            },
            {
                "action": ["destroy"],
                "principal": "authenticated",
                "effect": "allow",
                "condition": ("has_model_or_domain_or_obj_perms:core.delete_headercontentguard"),
            },
            {
                "action": ["list_roles", "add_role", "remove_role"],
                "principal": "authenticated",
                "effect": "allow",
                "condition": (
                    "has_model_or_domain_or_obj_perms:core.manage_roles_headercontentguard"
                ),
            },
        ],
        "creation_hooks": [
            {
                "function": "add_roles_for_object_creator",
                "parameters": {"roles": ["core.headercontentguard_owner"]},
            },
        ],
        "queryset_scoping": {"function": "scope_queryset"},
    }
    LOCKED_ROLES = {
        "core.headercontentguard_creator": ["core.add_headercontentguard"],
        "core.headercontentguard_owner": [
            "core.view_headercontentguard",
            "core.change_headercontentguard",
            "core.delete_headercontentguard",
            "core.manage_roles_headercontentguard",
        ],
        "core.headercontentguard_viewer": ["core.view_headercontentguard"],
    }


class CompositeContentGuardViewSet(ContentGuardViewSet, RolesMixin):
    """
    Content guard that queries a list-of content-guards for access permissions.
    """

    endpoint_name = "composite"
    queryset = CompositeContentGuard.objects.all()
    serializer_class = CompositeContentGuardSerializer
    queryset_filtering_required_permission = "core.view_compositecontentguard"

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
                "condition": "has_model_or_domain_perms:core.add_compositecontentguard",
            },
            {
                "action": ["retrieve", "my_permissions"],
                "principal": "authenticated",
                "effect": "allow",
                "condition": "has_model_or_domain_or_obj_perms:core." "view_compositecontentguard",
            },
            {
                "action": ["update", "partial_update"],
                "principal": "authenticated",
                "effect": "allow",
                "condition": ("has_model_or_domain_or_obj_perms:core.change_compositecontentguard"),
            },
            {
                "action": ["destroy"],
                "principal": "authenticated",
                "effect": "allow",
                "condition": ("has_model_or_domain_or_obj_perms:core.delete_compositecontentguard"),
            },
            {
                "action": ["list_roles", "add_role", "remove_role"],
                "principal": "authenticated",
                "effect": "allow",
                "condition": (
                    "has_model_or_domain_or_obj_perms:core.manage_roles_compositecontentguard"
                ),
            },
        ],
        "creation_hooks": [
            {
                "function": "add_roles_for_object_creator",
                "parameters": {"roles": ["core.compositecontentguard_owner"]},
            },
        ],
        "queryset_scoping": {"function": "scope_queryset"},
    }
    LOCKED_ROLES = {
        "core.compositecontentguard_creator": ["core.add_compositecontentguard"],
        "core.compositecontentguard_owner": [
            "core.view_compositecontentguard",
            "core.change_compositecontentguard",
            "core.delete_compositecontentguard",
            "core.manage_roles_compositecontentguard",
        ],
        "core.compositecontentguard_viewer": ["core.view_compositecontentguard"],
    }


class DistributionFilter(BaseFilterSet):
    # e.g.
    # /?name=foo
    # /?name__in=foo,bar
    # /?base_path__contains=foo
    # /?base_path__icontains=foo
    pulp_label_select = LabelFilter()
    with_content = DistributionWithContentFilter()

    class Meta:
        model = Distribution
        fields = {
            "name": NAME_FILTER_OPTIONS,
            "base_path": ["exact", "contains", "icontains", "in"],
            "repository": ["exact", "in"],
        }


class BaseDistributionViewSet(NamedModelViewSet):
    """
    Provides base viewset for Distributions.
    """

    endpoint_name = "distributions"
    queryset = Distribution.objects.all()
    serializer_class = DistributionSerializer
    filterset_class = DistributionFilter

    def get_queryset(self):
        """Apply optimizations for list endpoint."""
        qs = super().get_queryset()
        if getattr(self, "action", "") == "list":
            # Fetch info for DetailRelatedFields: repository, content_guard, remote, publication
            qs = qs.select_related("repository", "content_guard", "remote", "publication").only(
                *self.queryset.model.get_field_names(),
                "repository__pulp_type",
                "content_guard__pulp_type",
                "remote__pulp_type",
                "publication__pulp_type",
            )
        return qs

    def async_reserved_resources(self, instance):
        """Return resource that locks all Distributions."""
        return ["/api/v3/distributions/"]


class ListDistributionViewSet(BaseDistributionViewSet, mixins.ListModelMixin):
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


class ReadOnlyDistributionViewSet(
    BaseDistributionViewSet,
    mixins.RetrieveModelMixin,
    mixins.ListModelMixin,
):
    """
    Provides read and list methods for Distributions.
    """


class DistributionViewSet(
    ReadOnlyDistributionViewSet,
    AsyncCreateMixin,
    AsyncRemoveMixin,
    AsyncUpdateMixin,
    LabelsMixin,
):
    """
    Provides read and list methods and also provides asynchronous CUD methods to dispatch tasks
    with reservation that lock all Distributions preventing race conditions during base_path
    checking.
    """


class ArtifactDistributionViewSet(ReadOnlyDistributionViewSet):
    """
    ViewSet for ArtifactDistribution.
    """

    endpoint_name = "artifacts"
    queryset = ArtifactDistribution.objects.all()
    serializer_class = ArtifactDistributionSerializer
