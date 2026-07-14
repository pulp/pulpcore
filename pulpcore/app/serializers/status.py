from gettext import gettext as _

from rest_framework import serializers

from pulpcore.app.models import AppStatus


class AppStatusSerializer(serializers.ModelSerializer):
    name = serializers.CharField(help_text=_("The name of the worker."), read_only=True)
    last_heartbeat = serializers.DateTimeField(
        help_text=_("Timestamp of the last time the worker talked to the service."), read_only=True
    )
    versions = serializers.HStoreField(
        help_text=_("Versions of the components installed."), read_only=True
    )

    class Meta:
        model = AppStatus
        fields = ("name", "last_heartbeat", "versions")


class VersionSerializer(serializers.Serializer):
    """
    Serializer for the version information of Pulp components
    """

    component = serializers.CharField(help_text=_("Name of a versioned component of Pulp"))

    version = serializers.CharField(help_text=_("Version of the component (e.g. 3.0.0)"))

    package = serializers.CharField(help_text=_("Python package name providing the component"))

    module = serializers.CharField(help_text=_("Python module name of the component"))

    domain_compatible = serializers.BooleanField(
        help_text=_("Domain feature compatibility of component")
    )


class DatabaseConnectionSerializer(serializers.Serializer):
    """
    Serializer for the database connection information
    """

    connected = serializers.BooleanField(
        help_text=_("Info about whether the app can connect to the database")
    )


class DatabaseStatusSerializer(serializers.Serializer):
    """
    Serializer for the per-alias connectivity + migration-completeness status of a single
    `settings.DATABASES` entry (phase1-status-endpoint).
    """

    alias = serializers.CharField(help_text=_("The settings.DATABASES alias this entry reports on"))

    connected = serializers.BooleanField(
        help_text=_("Info about whether the app can connect to this database alias")
    )

    migrations_complete = serializers.BooleanField(
        help_text=_(
            "Whether this database alias has no pending migrations. Null if connectivity "
            "could not be established, since migration status can't be determined in that case."
        ),
        allow_null=True,
    )


class RedisConnectionSerializer(serializers.Serializer):
    """
    Serializer for information about the Redis connection
    """

    connected = serializers.BooleanField(
        help_text=_("Info about whether the app can connect to Redis")
    )


class StorageSerializer(serializers.Serializer):
    """
    Serializer for information about the storage system
    """

    total = serializers.IntegerField(
        min_value=0, help_text=_("Total number of bytes"), allow_null=True
    )

    used = serializers.IntegerField(
        min_value=0, help_text=_("Number of bytes in use"), allow_null=True
    )

    free = serializers.IntegerField(
        min_value=0, help_text=_("Number of free bytes"), allow_null=True
    )


class ContentSettingsSerializer(serializers.Serializer):
    """
    Serializer for information about content-app-settings for the pulp instance
    """

    content_origin = serializers.CharField(
        help_text=_("The CONTENT_ORIGIN setting for this Pulp instance"),
        allow_blank=False,
        allow_null=True,
        required=False,
    )
    content_path_prefix = serializers.CharField(
        help_text=_("The CONTENT_PATH_PREFIX setting for this Pulp instance"),
    )


class StatusSerializer(serializers.Serializer):
    """
    Serializer for the status information of the app
    """

    versions = VersionSerializer(help_text=_("Version information of Pulp components"), many=True)

    online_workers = AppStatusSerializer(
        help_text=_(
            "List of online workers known to the application. An online worker is actively "
            "heartbeating and can respond to new work."
        ),
        many=True,
    )

    online_api_apps = AppStatusSerializer(
        help_text=_(
            "List of online api apps known to the application. An online api app "
            "is actively heartbeating and can serve the rest api to clients."
        ),
        many=True,
    )

    online_content_apps = AppStatusSerializer(
        help_text=_(
            "List of online content apps known to the application. An online content app "
            "is actively heartbeating and can serve data to clients."
        ),
        many=True,
    )

    database_connection = DatabaseConnectionSerializer(
        help_text=_("Database connection information")
    )

    databases = DatabaseStatusSerializer(
        help_text=_(
            "Per-alias connectivity and migration-completeness status for every configured "
            "settings.DATABASES alias (one entry per alias, including 'default')."
        ),
        many=True,
    )

    redis_connection = RedisConnectionSerializer(
        required=False,
        help_text=_("Redis connection information"),
    )

    storage = StorageSerializer(required=False, help_text=_("Storage information"))

    content_settings = ContentSettingsSerializer(help_text=_("Content-app settings"))

    domain_enabled = serializers.BooleanField(help_text=_("Is Domains enabled"))
