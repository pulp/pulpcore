from django.conf import settings
from django.urls import path, include
from pulpcore.app.urls import API_ROOT, docs_and_status, special_views, all_routers

# Add all the Pulp API endpoints again, but with the API_ROOT as a path parameter
PATH_API_ROOT = "<path:api_root>/" + API_ROOT.split(settings.API_ROOT[1:])[1]
dup_urls = special_views + docs_and_status
for router in all_routers:
    dup_urls.extend(router.urls)

# dups_no_schema = [no_schema_view(p, name=p.name) for p in dup_urls]
urlpatterns = [path(PATH_API_ROOT, include(dup_urls))]
