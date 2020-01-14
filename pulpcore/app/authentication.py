from rest_framework.authentication import RemoteUserAuthentication

from pulpcore.app import settings


class PulpRemoteUserAuthentication(RemoteUserAuthentication):

    header = settings.REMOTE_USER_ENVIRON_NAME
