from pulpcore.app.models import Domain
from pulpcore.app.util import set_current_user_lazy, set_domain
from django.http.response import Http404


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
