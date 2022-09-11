import gettext
import logging

from asgiref.sync import sync_to_async
from aiohttp.web import middleware
from django.conf import settings
from django.db.utils import InterfaceError, OperationalError
from django.http.request import HttpRequest
from rest_framework.views import APIView
from rest_framework.exceptions import APIException

from .handler import Handler, PathNotResolved
from pulpcore.app.models import Domain
from pulpcore.app.util import set_domain

log = logging.getLogger(__name__)
_ = gettext.gettext


@middleware
async def authenticate(request, handler):
    """Authenticates the request to the content app using the DRF authentication classes"""
    django_request = convert_request(request)
    fake_view = APIView()

    def _authenticate_blocking():
        drf_request = fake_view.initialize_request(django_request)
        try:
            try:
                domain = validate_domain(request)
                fake_view.perform_authentication(drf_request)
            except (InterfaceError, OperationalError):
                Handler._reset_db_connection()
                domain = validate_domain(request)
                fake_view.perform_authentication(drf_request)

            setattr(drf_request, "pulp_domain", domain)
        except APIException as e:
            log.warning(_('"{} {}" "{}": {}').format(request.method, request.path, request.host, e))

        return drf_request

    auth_request = await sync_to_async(_authenticate_blocking)()
    request["user"] = auth_request.user
    request["auth"] = auth_request.auth
    request["drf_request"] = auth_request

    return await handler(request)


def convert_request(request):
    """
    Converts an aiohttp Request to a Django HttpRequest

    This does not convert the async body to a sync body for POST requests
    """
    djr = HttpRequest()
    djr.method = request.method
    upper_keys = {k.upper() for k in request.headers.keys()}
    # These two headers are specially set by Django without the HTTP prefix
    h = {"CONTENT_LENGTH", "CONTENT_TYPE"}
    djr.META = {f"HTTP_{k}" if k not in h else k: request.headers[k] for k in upper_keys}
    djr.COOKIES = request.cookies
    djr.path = request.path
    djr.path_info = request.match_info.get("path", "")
    djr.encoding = request.charset
    djr.GET = request.query

    djr._get_scheme = lambda: request.scheme
    return djr


def validate_domain(request):
    """
    Ensures the request is inside a proper Domain.
    """
    domain_name = request.match_info.get("pulp_domain", "default")
    try:
        domain = Domain.objects.get(name=domain_name)
    except Domain.DoesNotExist:
        path = request.match_info.get("path", "")
        if settings.DOMAIN_ENABLED:
            path = domain_name + "/" + path
        raise PathNotResolved(path)

    set_domain(domain)
    return domain
