import logging
import shutil
from gettext import gettext as _

from django.conf import settings
from django.core.files.storage import default_storage
from drf_yasg.utils import swagger_auto_schema
from pkg_resources import get_distribution
from rest_framework.response import Response
from rest_framework.views import APIView

from pulpcore.app.models.status import ContentAppStatus
from pulpcore.app.models.task import Worker
from pulpcore.app.serializers.status import StatusSerializer
from pulpcore.app.settings import INSTALLED_PULP_PLUGINS
from pulpcore.tasking.connection import get_redis_connection

_logger = logging.getLogger(__name__)


def _disk_usage():
    if settings.DEFAULT_FILE_STORAGE == "pulpcore.app.models.storage.FileSystem":
        try:
            return shutil.disk_usage(default_storage.location)
        except Exception:
            _logger.exception(_("Failed to determine disk usage"))

    return None


class StatusView(APIView):
    """
    Returns status information about the application
    """

    # allow anyone to access the status api
    authentication_classes = []
    permission_classes = []

    @swagger_auto_schema(
        operation_summary="Inspect status of Pulp",
        operation_id="status_read",
        responses={200: StatusSerializer},
    )
    def get(self, request, format=None):
        """
        Returns app information including the version of pulpcore and loaded pulp plugins,
        known workers, database connection status, and messaging connection status
        """
        components = ["pulpcore"] + INSTALLED_PULP_PLUGINS
        versions = [
            {"component": component, "version": get_distribution(component).version}
            for component in components
        ]
        redis_status = {"connected": self._get_redis_conn_status()}
        db_status = {"connected": self._get_db_conn_status()}

        try:
            online_workers = Worker.objects.online_workers()
        except Exception:
            online_workers = None

        try:
            online_content_apps = ContentAppStatus.objects.online()
        except Exception:
            online_content_apps = None

        data = {
            "versions": versions,
            "online_workers": online_workers,
            "online_content_apps": online_content_apps,
            "database_connection": db_status,
            "redis_connection": redis_status,
            "storage": _disk_usage(),
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
