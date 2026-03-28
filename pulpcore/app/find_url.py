from django.conf import settings

DOMAIN_SLUG = "<slug:pulp_domain>"
REWRITE_SLUG = "/<path:api_root>/"


# We isolate this utility-function to avoid pulling in random "Django App must be configured"
# code segments from the rest of the .util methods/imports
def find_api_root(version="v3", set_domain=True, domain=None, lstrip=False, rewrite_header=True):
    """
    Returns the tuple (api-root, <root>/api/<version>)

    Args:
        version (str): API-version desired
        set_domain (bool): Should the domain-slug be included if DOMAIN_ENABLED?
        domain (str): Domain-name to replace DOMAIN_SLUG
        lstrip (bool): Should the full version have it's leading-/ stripped
        rewrite_header (bool): Should API_ROOT_REWRITE_HEADER be honored or not

    Examples:
        find_api_root() : ("/pulp/", "/pulp/api/v3/")
        find_api_root(), DOMAIN_ENABLED: ("/pulp/", "/pulp/<slug:pulp_domain>/api/v3/")
        find_api_root(domain="default"), DOMAIN_ENABLED : ("/pulp/", "/pulp/default/api/v3/")
        find_api_root(lstrip=True) : ("pulp/", "pulp/api/v3/")
        find_api_root(), API_ROOT_REWRITE_HEADER: ("/<path:api_root>/", "/<path:api_root>/api/v3/")
        find_api_root(version="v4", domain="foo", lstrip=True), API_ROOT_REWRITE_HEADER :
            ("<path:api_root>/", "<path:api_root>/default/api/v4/")
    Returns:
        (str, str) : (API_ROOT (possibly re-written), API_ROOT/api/<version>/
                     (with <domain> if enabled))
    """
    # Some current path-building wants to ignore REWRITE - make that possible
    if rewrite_header and settings.API_ROOT_REWRITE_HEADER:
        api_root = REWRITE_SLUG
    else:
        api_root = settings.API_ROOT

    # Some current path-building wants to ignore DOMAIN - make that possible
    if set_domain and settings.DOMAIN_ENABLED:
        if domain:
            path = f"{api_root}{domain}/api/{version}/"
        else:
            path = f"{api_root}{DOMAIN_SLUG}/api/{version}/"
    else:
        path = f"{api_root}api/{version}/"
    if lstrip:
        return api_root.lstrip("/"), path.lstrip("/")
    else:
        return api_root, path
