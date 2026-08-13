"""pulp URL Configuration"""

from django.conf import settings
from django.urls import include, path, re_path
from django.views.decorators.cache import cache_page
from drf_spectacular.utils import extend_schema
from drf_spectacular.views import (
    SpectacularJSONAPIView,
    SpectacularRedocView,
    SpectacularSwaggerView,
    SpectacularYAMLAPIView,
)
from rest_framework.routers import APIRootView
from rest_framework_nested import routers

from pulpcore.app.apps import pulp_plugin_configs
from pulpcore.app.views import (
    DataRepair7272View,
    LivezView,
    OrphansView,
    PulpImporterImportCheckView,
    RepairView,
    StatusView,
)
from pulpcore.app.viewsets import (
    ListRepositoryVersionViewSet,
    LoginViewSet,
    OrphansCleanupViewset,
    ReclaimSpaceViewSet,
)
from pulpcore.plugin.find_url import find_api_root

HUNDRED_DAYS = 100 * 24 * 60 * 60


def _setup_vars(vers=settings.REST_FRAMEWORK.get("DEFAULT_VERSION", "v3")):
    _, PATH_DOMAIN_REWRITE_NOFRONT = find_api_root(
        lstrip=True, set_domain=True, rewrite_header=True, version=vers
    )
    _, PATH_NODOMAIN_NOREWRITE_NOFRONT = find_api_root(
        lstrip=True, set_domain=False, rewrite_header=False, version=vers
    )
    _, PATH_NODOMAIN_REWRITE_NOFRONT = find_api_root(
        lstrip=True, set_domain=False, rewrite_header=True, version=vers
    )
    return {
        "PATH_DOMAIN_REWRITE_NOFRONT": PATH_DOMAIN_REWRITE_NOFRONT,
        "PATH_NODOMAIN_NOREWRITE_NOFRONT": PATH_NODOMAIN_NOREWRITE_NOFRONT,
        "PATH_NODOMAIN_REWRITE_NOFRONT": PATH_NODOMAIN_REWRITE_NOFRONT,
    }


if settings.ENABLE_V4_API:
    VERSIONS = [r"<str:version>"]
else:
    VERSIONS = [r"v3"]

PATH_VARS = {}
for v in VERSIONS:
    PATH_VARS[v] = _setup_vars(vers=v)


def _docs_and_status(version):
    return [
        re_path(r"^livez/", LivezView.as_view()),
        re_path(r"^status/$", StatusView.as_view()),
        re_path(
            r"^docs/api.json$",
            cache_page(HUNDRED_DAYS)(
                SpectacularJSONAPIView.as_view(authentication_classes=[], permission_classes=[])
            ),
            name="schema",
        ),
        re_path(
            r"^docs/api.yaml$",
            cache_page(HUNDRED_DAYS)(
                SpectacularYAMLAPIView.as_view(authentication_classes=[], permission_classes=[])
            ),
            name="schema-yaml",
        ),
        re_path(
            r"^docs/$",
            cache_page(HUNDRED_DAYS)(
                SpectacularRedocView.as_view(
                    authentication_classes=[],
                    permission_classes=[],
                    url=f"/{PATH_VARS[version]['PATH_NODOMAIN_NOREWRITE_NOFRONT']}docs/api.json?include_html=1&pk_path=1",
                )
            ),
            name="schema-redoc",
        ),
        re_path(
            r"^swagger/$",
            cache_page(HUNDRED_DAYS)(
                SpectacularSwaggerView.as_view(
                    authentication_classes=[],
                    permission_classes=[],
                    url=f"/{PATH_VARS[version]['PATH_NODOMAIN_NOREWRITE_NOFRONT']}docs/api.json?include_html=1&pk_path=1",
                )
            ),
            name="schema-swagger",
        ),
    ]


for v in VERSIONS:
    PATH_VARS[v]["docs_and_status"] = _docs_and_status(v)


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
        if not node.viewset.routable():
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


class PulpAPIRootView(APIRootView):
    """A Pulp-defined APIRootView class with no authentication requirements."""

    authentication_classes = []
    permission_classes = []

    def get(self, request, *args, **kwargs):
        if settings.DOMAIN_ENABLED:
            kwargs["pulp_domain"] = request.pulp_domain.name
        if api_root := getattr(request, "api_root", None):
            kwargs["api_root"] = api_root
        return super().get(request, *args, **kwargs)


class PulpDefaultRouter(routers.DefaultRouter):
    """A DefaultRouter class that benefits from the customized PulpAPIRootView class."""

    APIRootView = PulpAPIRootView


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

special_views = [
    re_path(r"^login/$", LoginViewSet.as_view()),
    re_path(r"^repair/$", RepairView.as_view()),
    re_path(r"^datarepair/7272/$", DataRepair7272View.as_view()),
    re_path(
        r"^orphans/cleanup/$",
        OrphansCleanupViewset.as_view(actions={"post": "cleanup"}),
    ),
    re_path(r"^orphans/$", OrphansView.as_view()),
    re_path(
        r"^repository_versions/$",
        ListRepositoryVersionViewSet.as_view(actions={"get": "list"}),
    ),
    re_path(
        r"^repositories/reclaim_space/$",
        ReclaimSpaceViewSet.as_view(actions={"post": "reclaim"}),
    ),
    re_path(
        r"^importers/core/pulp/import-check/$",
        PulpImporterImportCheckView.as_view(),
    ),
]

urlpatterns = [path("auth/", include("rest_framework.urls"))]
if "social_django" in settings.INSTALLED_APPS:
    urlpatterns.append(
        path("", include("social_django.urls", namespace=settings.SOCIAL_AUTH_URL_NAMESPACE))
    )

if "djangosaml2" in settings.INSTALLED_APPS:
    urlpatterns.append(path("saml2/", include("djangosaml2.urls")))

for v in VERSIONS:
    tmp_list = [
        path(PATH_VARS[v]["PATH_DOMAIN_REWRITE_NOFRONT"], include(special_views)),
        # docs/status aren't "inside" a domain
        path(
            PATH_VARS[v]["PATH_NODOMAIN_REWRITE_NOFRONT"], include(PATH_VARS[v]["docs_and_status"])
        ),
    ]
    urlpatterns.extend(tmp_list)
    if settings.DOMAIN_ENABLED:
        # Ensure Docs and Status endpoints are available within domains, but are not shown in API schema
        docs_and_status_no_schema = []
        for p in PATH_VARS[v]["docs_and_status"]:

            @extend_schema(exclude=True)
            class NoSchema(p.callback.cls):
                pass

            view = NoSchema.as_view(**p.callback.initkwargs)
            name = p.name + "-domains" if p.name else None
            pattern = rf"^{str(p.pattern)}$"
            docs_and_status_no_schema.append(re_path(pattern, view, name=name))
        urlpatterns.insert(
            -1,
            path(PATH_VARS[v]["PATH_DOMAIN_REWRITE_NOFRONT"], include(docs_and_status_no_schema)),
        )

for v in VERSIONS:
    # The Pulp Platform API router, which can be used to manually register ViewSets with the API.
    root_router = PulpDefaultRouter()

    all_routers = [root_router] + vs_tree.register_with(root_router)
    for router in all_routers:
        urlpatterns.append(path(PATH_VARS[v]["PATH_DOMAIN_REWRITE_NOFRONT"], include(router.urls)))

# If plugins define a urls.py, include them into the root namespace.
for plugin_pattern in plugin_patterns:
    urlpatterns.append(path("", include(plugin_pattern)))
