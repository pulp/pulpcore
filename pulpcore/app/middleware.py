from django.contrib.auth.middleware import RemoteUserMiddleware

from pulpcore.app import settings


class PulpRemoteUserMiddleware(RemoteUserMiddleware):
    header = settings.REMOTE_USER_ENVIRON_NAME
