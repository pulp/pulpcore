from rest_framework import mixins

from pulpcore.app.models import ContentView
from pulpcore.app.serializers import ContentViewSerializer
from pulpcore.app.viewsets import LabelsMixin, NamedModelViewSet, RolesMixin
from pulpcore.app.viewsets.base import NAME_FILTER_OPTIONS
from pulpcore.app.viewsets.custom_filters import LabelFilter
from pulpcore.filters import BaseFilterSet


class ContentViewFilter(BaseFilterSet):
    """FilterSet for ContentView."""

    pulp_label_select = LabelFilter()

    class Meta:
        model = ContentView
        fields = {"name": NAME_FILTER_OPTIONS}


class ContentViewViewSet(
    NamedModelViewSet,
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.ListModelMixin,
    mixins.UpdateModelMixin,
    mixins.DestroyModelMixin,
    RolesMixin,
    LabelsMixin,
):
    """
    ViewSet for ContentView.

    A ContentView is a named, persistable scope composed of Distributions -- potentially
    spanning multiple domains -- that plugins can search across (see each plugin's
    ``content-views/{content_view_pk}/search/...`` nested endpoints for the actual search
    operations; this viewset only provides the standard CRUD lifecycle for the resource itself).
    """

    queryset = ContentView.objects.all()
    endpoint_name = "content-views"
    serializer_class = ContentViewSerializer
    filterset_class = ContentViewFilter
    ordering = "-pulp_created"
    queryset_filtering_required_permission = "core.view_contentview"

    DEFAULT_ACCESS_POLICY = {
        "statements": [
            {
                "action": ["list", "my_permissions"],
                "principal": "authenticated",
                "effect": "allow",
            },
            {
                "action": ["create"],
                "principal": "authenticated",
                "effect": "allow",
                "condition": "has_model_or_domain_perms:core.add_contentview",
            },
            {
                "action": ["retrieve"],
                "principal": "authenticated",
                "effect": "allow",
                "condition": "has_model_or_domain_or_obj_perms:core.view_contentview",
            },
            {
                "action": ["update", "partial_update", "set_label", "unset_label"],
                "principal": "authenticated",
                "effect": "allow",
                "condition": "has_model_or_domain_or_obj_perms:core.change_contentview",
            },
            {
                "action": ["destroy"],
                "principal": "authenticated",
                "effect": "allow",
                "condition": "has_model_or_domain_or_obj_perms:core.delete_contentview",
            },
            {
                "action": ["list_roles", "add_role", "remove_role"],
                "principal": "authenticated",
                "effect": "allow",
                "condition": "has_model_or_domain_or_obj_perms:core.manage_roles_contentview",
            },
        ],
        "creation_hooks": [
            {
                "function": "add_roles_for_object_creator",
                "parameters": {"roles": "core.contentview_owner"},
            },
        ],
        "queryset_scoping": {"function": "scope_queryset"},
    }

    LOCKED_ROLES = {
        "core.contentview_creator": ["core.add_contentview"],
        "core.contentview_owner": [
            "core.view_contentview",
            "core.change_contentview",
            "core.delete_contentview",
            "core.manage_roles_contentview",
        ],
        "core.contentview_viewer": ["core.view_contentview"],
    }
