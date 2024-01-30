from pulpcore.app.models import Domain
from pulpcore.app.util import set_current_user_lazy, set_domain
from django.http.response import Http404
from django.conf import settings
from django.core.exceptions import MiddlewareNotUsed
from django.urls import set_urlconf


class DomainMiddleware:
    """
    A middleware class to add in the domain name to the request context.

    Removes the domain name from the view kwargs if present in the url. If no domain is specified
    "default" is used.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Code to be executed for each request before
        # the view (and later middleware) are called.

        # Determine user lazy, because authentication has not happened yet.
        set_current_user_lazy(lambda: request.user)

        response = self.get_response(request)

        # Code to be executed for each request/response after
        # the view is called.

        return response

    def process_view(self, request, view_func, view_args, view_kwargs):
        """Remove the domain name if present, called right before view_func is called."""
        domain_name = view_kwargs.pop("pulp_domain", "default")
        try:
            domain = Domain.objects.get(name=domain_name)
        except Domain.DoesNotExist:
            raise Http404()
        set_domain(domain)
        setattr(request, "pulp_domain", domain)
        return None


class APIRootRewriteMiddleware:
    """
    A middleware class to support API_ROOT_REWRITE_HEADER setting.

    When API_ROOT_REWRITE_HEADER is set, this middleware will check for the existence of the header
    on the request and if set it will add the new API_ROOT to the request context and remove the
    path from the view_kwargs. If the header API_ROOT does not match the url path's API_ROOT this
    middleware will return a 404. If the header is not set on the request this middleware does
    nothing.

    When API_ROOT_REWRITE_HEADER is not set, this middleware will be marked as unused.
    """

    def __init__(self, get_response):
        if not settings.API_ROOT_REWRITE_HEADER:
            raise MiddlewareNotUsed()
        self.get_response = get_response

    def __call__(self, request):
        # Code to be executed for each request before
        # the view (and later middleware) are called.
        if new_api_root := request.headers.get(settings.API_ROOT_REWRITE_HEADER):
            setattr(request, 'api_root', new_api_root)
            setattr(request, 'urlconf', 'pulpcore.app.path_api_urls')
            set_urlconf('pulpcore.app.path_api_urls')

        response = self.get_response(request)

        # Code to be executed for each request/response after
        # the view is called.
        # Should we add a header to the response to indicate the API_ROOT has been rewritten?

        return response

    def process_view(self, request, view_func, view_args, view_kwargs):
        if new_api_root := getattr(request, 'api_root', None):
            # Ensure that the requested URL's API_ROOT matches the header's API_ROOT
            # Should I be less strict in the check and strip '/' from beginning and end?
            api_root = view_kwargs.pop('api_root', None)
            if api_root and api_root != new_api_root:
                raise Http404()

        return None
