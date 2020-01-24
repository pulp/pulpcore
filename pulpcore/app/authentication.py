from django.contrib.auth.backends import RemoteUserBackend
from rest_framework.authentication import RemoteUserAuthentication

from pulpcore.app import settings


class PulpRemoteUserAuthentication(RemoteUserAuthentication):

    header = settings.REMOTE_USER_ENVIRON_NAME


class PulpNoCreateRemoteUserBackend(RemoteUserBackend):

    create_unknown_user = False  # Configure RemoteUserBackend to not create users
