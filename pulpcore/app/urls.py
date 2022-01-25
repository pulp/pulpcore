"""pulp URL Configuration"""
import logging

from django.conf import settings
from django.contrib import admin
from django.urls import path, include
from drf_spectacular.views import (
    SpectacularJSONAPIView,
    SpectacularYAMLAPIView,
    SpectacularRedocView,
)
from rest_framework_nested import routers

from pulpcore.app.apps import pulp_plugin_configs
from pulpcore.app.views import OrphansView, PulpImporterImportCheckView, RepairView, StatusView
from pulpcore.app.viewsets import (
    ListRepositoryVersionViewSet,
    OrphansCleanupViewset,
    ReclaimSpaceViewSet,
)

log = logging.getLogger(__name__)

API_ROOT = settings.V3_API_ROOT_NO_FRONT_SLASH


class ViewSetNode:
    """
    Each node is a tree that can register nested ViewSets with DRF nested routers.

    The structure of the tree becomes the url heirarchy when the ViewSets are registered.

    Example Structure:

        RootNode
        ├─ RepositoryViewSet
        │  ├─ PluginPublisherViewSet (non-nested)
        │  │  └─ PluginPublisherVDistributionViewSet
        │  ├─ AnotherPluginPublisherViewSet
        │  │  └─ AnotherPluginDistributionViewSet
        │  └─ FileRemoteViewSet
        └─ some-non-nested viewset
    """

    def __init__(self, viewset=None):
        """
        Create a new node.

        Args:
            viewset (pulpcore.app.viewsets.base.NamedModelViewSet): If provided, represent this
                viewset. If not provided, this is the root node.
        """
        self.viewset = viewset
        self.children = []

    def add_decendent(self, node):
        """
        Add a VSNode to the tree. If node is not a direct child, attempt to add the to each child.

        Args:
            node (ViewSetNode): A node that represents a viewset and its decendents.
        """
        # Master viewsets do not have endpoints, so they do not need to be registered
        if node.viewset.is_master_viewset():
            return
        # Non-nested viewsets are attached to the root node
        if not node.viewset.parent_viewset:
            self.children.append(node)
        # The node is a direct child if the child.parent_viewset is self.viewset.
        elif self.viewset and self.viewset is node.viewset.parent_viewset:
            self.children.append(node)
        else:
            for child in self.children:
                child.add_decendent(node)

    def register_with(self, router):
        """
        Register this tree with the specified router and create new routers as necessary.

        Args:
            router (routers.DefaultRouter): router to register the viewset with.
            created_routers (list): A running list of all routers.
        Returns:
            list: List of new routers, including those created recursively.
        """
        created_routers = []
        # Root node does not need to be registered, and it doesn't need a router either.
        if self.viewset:
            router.register(self.viewset.urlpattern(), self.viewset, self.viewset.view_name())
            if self.children:
                router = routers.NestedDefaultRouter(
                    router, self.viewset.urlpattern(), lookup=self.viewset.router_lookup
                )
                created_routers.append(router)
        # If we created a new router for the parent, recursively register the children with it
        for child in self.children:
            created_routers = created_routers + child.register_with(router)
        return created_routers

    def __repr__(self):
        if not self.viewset:
            return "Root"
        else:
            return str(self.viewset)


all_viewsets = []
plugin_patterns = []
# Iterate over each app, including pulpcore and the plugins.
for app_config in pulp_plugin_configs():
    for viewsets in app_config.named_viewsets.values():
        all_viewsets.extend(viewsets)
    if app_config.urls_module:
        plugin_patterns.append(app_config.urls_module)

sorted_by_depth = sorted(all_viewsets, key=lambda vs: vs._get_nest_depth())
vs_tree = ViewSetNode()
for viewset in sorted_by_depth:
    vs_tree.add_decendent(ViewSetNode(viewset))

#: The Pulp Platform v3 API router, which can be used to manually register ViewSets with the API.
root_router = routers.DefaultRouter()

urlpatterns = [
    path(f"{API_ROOT}repair/", RepairView.as_view()),
    path(f"{API_ROOT}status/", StatusView.as_view()),
    path(
        f"{API_ROOT}orphans/cleanup/",
        OrphansCleanupViewset.as_view({"post": "cleanup"}),
    ),
    path(f"{API_ROOT}orphans/", OrphansView.as_view()),
    path(
        f"{API_ROOT}repository_versions/",
        ListRepositoryVersionViewSet.as_view({"get": "list"}),
    ),
    path(
        f"{API_ROOT}repositories/reclaim_space/",
        ReclaimSpaceViewSet.as_view({"post": "reclaim"}),
    ),
    path(
        f"{API_ROOT}importers/core/pulp/import-check/",
        PulpImporterImportCheckView.as_view(),
    ),
    path("auth/", include("rest_framework.urls")),
    path(settings.ADMIN_SITE_URL, admin.site.urls),
]

urlpatterns.append(
    path(
        f"{API_ROOT}docs/api.json",
        SpectacularJSONAPIView.as_view(authentication_classes=[], permission_classes=[]),
        name="schema",
    )
)

urlpatterns.append(
    path(
        f"{API_ROOT}docs/api.yaml",
        SpectacularYAMLAPIView.as_view(authentication_classes=[], permission_classes=[]),
        name="schema-yaml",
    )
)

urlpatterns.append(
    path(
        f"{API_ROOT}docs/",
        SpectacularRedocView.as_view(
            authentication_classes=[],
            permission_classes=[],
            url=f"{settings.V3_API_ROOT}docs/api.json?include_html=1",
        ),
        name="schema-redoc",
    )
)

all_routers = [root_router] + vs_tree.register_with(root_router)
for router in all_routers:
    urlpatterns.append(path(API_ROOT, include(router.urls)))

# If plugins define a urls.py, include them into the root namespace.
for plugin_pattern in plugin_patterns:
    urlpatterns.append(path("", include(plugin_pattern)))
