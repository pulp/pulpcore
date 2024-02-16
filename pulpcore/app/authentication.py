import json
import jq
import logging

from base64 import b64decode
from binascii import Error as Base64DecodeError
from gettext import gettext as _

from django.contrib.auth import authenticate
from django.contrib.auth.backends import RemoteUserBackend
from rest_framework.authentication import BaseAuthentication, RemoteUserAuthentication
from rest_framework.exceptions import AuthenticationFailed

from pulpcore.app import settings

_logger = logging.getLogger(__name__)


class PulpRemoteUserAuthentication(RemoteUserAuthentication):
    header = settings.REMOTE_USER_ENVIRON_NAME


class PulpNoCreateRemoteUserBackend(RemoteUserBackend):
    create_unknown_user = False  # Configure RemoteUserBackend to not create users


class JSONHeaderRemoteAuthentication(BaseAuthentication):
    """
    Authenticate users based on a jq filter applied to a specific header.

    For users logging in first time it creates User record.
    """

    header = settings.AUTHENTICATION_JSON_HEADER
    jq_filter = settings.AUTHENTICATION_JSON_HEADER_JQ_FILTER

    def authenticate(self, request):
        """
        Checks for the presence of a header, and if its content is able
        to be filtered by JQ.
        """
        if self.header not in request.META:
            _logger.debug(
                "Access not allowed. Header {header} not found.".format(header=self.header)
            )
            return None

        try:
            header_content = request.META.get(self.header)
            header_decoded_content = b64decode(header_content)
        except Base64DecodeError:
            _logger.debug(_("Access not allowed - Header content is not Base64 encoded."))
            raise AuthenticationFailed(_("Access denied."))

        try:
            header_value = json.loads(header_decoded_content)
            json_path = jq.compile(self.jq_filter)

            remote_user = json_path.input_value(header_value).first()
        except json.JSONDecodeError:
            _logger.debug(_("Access not allowed - Invalid JSON."))
            raise AuthenticationFailed(_("Access denied. Invalid JSON."))

        if not remote_user:
            _logger.debug(_("Path or value not found."))
            return None

        user = authenticate(request, remote_user=remote_user)

        if not user:
            return None

        _logger.debug(_("User {user} authenticated.").format(user=remote_user))
        return (user, None)
