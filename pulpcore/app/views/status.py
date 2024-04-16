import logging
import shutil
from gettext import gettext as _

from django.conf import settings
from django.db.models import Sum
from drf_spectacular.utils import extend_schema
from rest_framework.response import Response
from rest_framework.views import APIView
from collections import namedtuple

from pulpcore.app.apps import pulp_plugin_configs
from pulpcore.app.models.content import Artifact
from pulpcore.app.models.status import ApiAppStatus, ContentAppStatus
from pulpcore.app.models.task import Worker
from pulpcore.app.serializers.status import StatusSerializer
from pulpcore.app.redis_connection import get_redis_connection
from pulpcore.app.util import get_domain

_logger = logging.getLogger(__name__)
StorageSpace = namedtuple("StorageSpace", ("total", "used", "free"))


def _disk_usage():
    domain = get_domain()
    if domain.storage_class == "pulpcore.app.models.storage.FileSystem":
        storage = domain.get_storage()
        try:
            return shutil.disk_usage(storage.location)
        except Exception:
            _logger.exception(_("Failed to determine disk usage"))
    else:
        used = Artifact.objects.filter(pulp_domain=domain).aggregate(size=Sum("size", default=0))
        return StorageSpace(None, used["size"], None)


class StatusView(APIView):
    """
    Returns status information about the application
    """

    # allow anyone to access the status api
    authentication_classes = []
    permission_classes = []

    @extend_schema(
        summary="Inspect status of Pulp",
        operation_id="status_read",
        responses={200: StatusSerializer},
    )
    def get(self, request):
        """
        Returns status and app information about Pulp.

        Information includes:
         * version of pulpcore and loaded pulp plugins
         * known workers
         * known content apps
         * database connection status
         * redis connection status
         * disk usage information
        """
        versions = []
        for app in pulp_plugin_configs():
            versions.append(
                {
                    "component": app.label,
                    "version": app.version,
                    "package": app.python_package_name,
                    "module": app.name,
                    "domain_compatible": getattr(app, "domain_compatible", False),
                }
            )

        if settings.CACHE_ENABLED:
            redis_status = {"connected": self._get_redis_conn_status()}
        else:
            redis_status = {"connected": False}

        db_status = {"connected": self._get_db_conn_status()}

        online_workers = Worker.objects.online()
        online_api_apps = ApiAppStatus.objects.online()
        online_content_apps = ContentAppStatus.objects.online()

        content_settings = {
            "content_origin": settings.CONTENT_ORIGIN,
            "content_path_prefix": settings.CONTENT_PATH_PREFIX,
        }

        data = {
            "versions": versions,
            "online_workers": online_workers,
            "online_api_apps": online_api_apps,
            "online_content_apps": online_content_apps,
            "database_connection": db_status,
            "redis_connection": redis_status,
            "storage": _disk_usage(),
            "content_settings": content_settings,
            "domain_enabled": settings.DOMAIN_ENABLED,
        }

        context = {"request": request}
        serializer = StatusSerializer(data, context=context)
        return Response(serializer.data)

    @staticmethod
    def _get_db_conn_status():
        """
        Returns True if pulp is connected to the database

        Returns:
            bool: True if there's a db connection. False otherwise.
        """
        try:
            Worker.objects.count()
        except Exception:
            _logger.exception(_("Cannot connect to database during status check."))
            return False
        else:
            return True

    @staticmethod
    def _get_redis_conn_status():
        """
        Returns True if pulp can connect to Redis

        Returns:
            bool: True if pulp can connect to Redis. False otherwise.
        """
        conn = get_redis_connection()
        try:
            conn.ping()
        except Exception:
            _logger.error(_("Connection to Redis failed during status check!"))
            return False
        else:
            return True


class LivezView(APIView):
    """
    Liveness Probe for the REST API.
    """

    # allow anyone to access the liveness api
    authentication_classes = []
    permission_classes = []

    @extend_schema(
        summary="Inspect liveness of Pulp's REST API.",
        operation_id="livez_read",
        responses={200: None},
    )
    def get(self, request):
        """
        Returns 200 OK when API is alive.
        """
        return Response()
