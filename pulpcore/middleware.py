import time
import re

from contextvars import ContextVar
from os import environ

from django.http.response import Http404
from django.conf import settings
from django.core.exceptions import MiddlewareNotUsed

from pulpcore.metrics import init_otel_meter
from pulpcore.app.models import Domain
from pulpcore.app.util import (
    get_worker_name,
    normalize_http_status,
    set_current_user_lazy,
    set_domain,
)

x_task_diagnostics_var = ContextVar("x_profile_task")


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
    middleware will return a 404. If the header is not set on the request this middleware will set
    `api_root` on the request context to the default setting's API_ROOT value.

    When API_ROOT_REWRITE_HEADER is not set, this middleware will be marked as unused.
    """

    def __init__(self, get_response):
        if not settings.API_ROOT_REWRITE_HEADER:
            raise MiddlewareNotUsed()
        self.get_response = get_response

    def __call__(self, request):
        # Code to be executed for each request before
        # the view (and later middleware) are called.
        if settings.API_ROOT_REWRITE_HEADER in request.headers:
            api_root = request.headers[settings.API_ROOT_REWRITE_HEADER].strip("/")
        else:
            api_root = settings.API_ROOT.strip("/")
        setattr(request, "api_root", api_root)

        response = self.get_response(request)

        # Code to be executed for each request/response after
        # the view is called.
        # Should we add a header to the response to indicate the API_ROOT has been rewritten?

        return response

    def process_view(self, request, view_func, view_args, view_kwargs):
        # Ensure that the requested URL's API_ROOT matches the header's/default API_ROOT
        api_root = view_kwargs.pop("api_root", None)
        if api_root and api_root != request.api_root:
            raise Http404()

        return None


class DjangoMetricsMiddleware:
    def __init__(self, get_response):
        self.meter = init_otel_meter("pulp-api")
        self._set_histogram(self.meter)

        self.get_response = get_response

    def _excluded_urls(self, url):

        excluded_urls = environ.get(
            "OTEL_PYTHON_EXCLUDED_URLS", environ.get("OTEL_PYTHON_DJANGO_EXCLUDED_URLS", "")
        )

        if excluded_urls:
            excluded_urls_list = [excluded_url.strip() for excluded_url in excluded_urls.split(",")]
        else:
            return False

        exclusion_pattern = "|".join(excluded_urls_list)

        if re.search(exclusion_pattern, url):
            return True

        return False

    def __call__(self, request):
        if self._excluded_urls(request.build_absolute_uri("?")):
            return self.get_response(request)

        start_time = time.time()
        response = self.get_response(request)
        end_time = time.time()

        duration_ms = (end_time - start_time) * 1000
        attributes = self._process_attributes(request, response)

        self.request_duration_histogram.record(duration_ms, attributes=attributes)

        return response

    def _set_histogram(self, meter):
        create_histogram_kwargs = {
            "name": "api.request_duration",
            "description": "Tracks the duration of HTTP requests",
            "unit": "ms",
        }

        if settings.OTEL_PULP_API_HISTOGRAM_BUCKETS:
            create_histogram_kwargs["explicit_bucket_boundaries_advisory"] = (
                settings.OTEL_PULP_API_HISTOGRAM_BUCKETS
            )

        self.request_duration_histogram = meter.create_histogram(**create_histogram_kwargs)

    def _process_attributes(self, request, response):
        return {
            "http.method": request.method,
            "http.status_code": normalize_http_status(response.status_code),
            "http.target": self._process_path(request, response),
            "worker.name": get_worker_name(),
        }

    @staticmethod
    def _process_path(request, response):
        # to prevent cardinality explosion, do not record invalid paths
        if response.status_code > 400:
            return ""

        # these attributes are initialized in the django's process_view method
        match = getattr(request, "resolver_match", "")
        route = getattr(match, "route", "")
        return route


class TaskProfilerMiddleware:
    """
    Middleware that looks for the presence of X-TASK-DIAGNOSTICS header and provides its value
    as a ContextVar to the dispatch() method in the tasking system. It enables generating
    profiling data of tasks dispatched via API.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if "HTTP_X_TASK_DIAGNOSTICS" in request.META:
            task_diagnostics = request.META["HTTP_X_TASK_DIAGNOSTICS"]
            ctx_token = x_task_diagnostics_var.set(task_diagnostics.split(","))
            try:
                return self.get_response(request)
            finally:
                x_task_diagnostics_var.reset(ctx_token)
        else:
            return self.get_response(request)
