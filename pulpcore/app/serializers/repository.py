from gettext import gettext as _
import os

from rest_framework import fields, serializers
from rest_framework.validators import UniqueValidator
from rest_framework_nested.serializers import NestedHyperlinkedModelSerializer

from pulpcore.app import models, settings
from pulpcore.app.serializers import (
    DetailIdentityField,
    DetailRelatedField,
    LatestVersionField,
    ModelSerializer,
    RepositoryVersionIdentityField,
    RepositoryVersionRelatedField,
    RepositoryVersionsIdentityFromRepositoryField,
    ValidateFieldsMixin,
)


class RepositorySerializer(ModelSerializer):
    pulp_href = DetailIdentityField(view_name_pattern=r"repositories(-.*/.*)-detail")
    versions_href = RepositoryVersionsIdentityFromRepositoryField()
    latest_version_href = LatestVersionField()
    name = serializers.CharField(
        help_text=_("A unique name for this repository."),
        validators=[UniqueValidator(queryset=models.Repository.objects.all())],
    )
    description = serializers.CharField(
        help_text=_("An optional description."), required=False, allow_null=True
    )
    remote = DetailRelatedField(
        view_name_pattern=r"remotes(-.*/.*)-detail",
        queryset=models.Remote.objects.all(),
        required=False,
        allow_null=True,
    )

    def validate_remote(self, value):
        if value and type(value) not in self.Meta.model.REMOTE_TYPES:
            raise serializers.ValidationError(
                detail=_("Type for Remote '{}' does not match Repository.").format(value.name)
            )

        return value

    class Meta:
        model = models.Repository
        fields = ModelSerializer.Meta.fields + (
            "versions_href",
            "latest_version_href",
            "name",
            "description",
            "remote",
        )


class RemoteSerializer(ModelSerializer):
    """
    Every remote defined by a plugin should have a Remote serializer that inherits from this
    class. Please import from `pulpcore.plugin.serializers` rather than from this module directly.
    """

    pulp_href = DetailIdentityField(view_name_pattern=r"remotes(-.*/.*)-detail")
    name = serializers.CharField(
        help_text=_("A unique name for this remote."),
        validators=[UniqueValidator(queryset=models.Remote.objects.all())],
    )
    url = serializers.CharField(help_text="The URL of an external content source.")
    ca_cert = serializers.CharField(
        help_text="A PEM encoded CA certificate used to validate the server "
        "certificate presented by the remote server.",
        required=False,
        allow_null=True,
    )
    client_cert = serializers.CharField(
        help_text="A PEM encoded client certificate used for authentication.",
        required=False,
        allow_null=True,
    )
    client_key = serializers.CharField(
        help_text="A PEM encoded private key used for authentication.",
        required=False,
        allow_null=True,
    )
    tls_validation = serializers.BooleanField(
        help_text="If True, TLS peer validation must be performed.", required=False
    )
    proxy_url = serializers.CharField(
        help_text="The proxy URL. Format: scheme://user:password@host:port",
        required=False,
        allow_null=True,
    )
    username = serializers.CharField(
        help_text="The username to be used for authentication when syncing.",
        required=False,
        allow_null=True,
    )
    password = serializers.CharField(
        help_text="The password to be used for authentication when syncing.",
        required=False,
        allow_null=True,
    )
    pulp_last_updated = serializers.DateTimeField(
        help_text="Timestamp of the most recent update of the remote.", read_only=True
    )
    download_concurrency = serializers.IntegerField(
        help_text="Total number of simultaneous connections.", required=False, min_value=1
    )
    policy = serializers.ChoiceField(
        help_text="The policy to use when downloading content.",
        choices=((models.Remote.IMMEDIATE, "When syncing, download all metadata and content now.")),
        default=models.Remote.IMMEDIATE,
    )

    total_timeout = serializers.FloatField(
        allow_null=True,
        required=False,
        help_text="aiohttp.ClientTimeout.total (q.v.) for download-connections.",
        min_value=0.0,
    )
    connect_timeout = serializers.FloatField(
        allow_null=True,
        required=False,
        help_text="aiohttp.ClientTimeout.connect (q.v.) for download-connections.",
        min_value=0.0,
    )
    sock_connect_timeout = serializers.FloatField(
        allow_null=True,
        required=False,
        help_text="aiohttp.ClientTimeout.sock_connect (q.v.) for download-connections.",
        min_value=0.0,
    )
    sock_read_timeout = serializers.FloatField(
        allow_null=True,
        required=False,
        help_text="aiohttp.ClientTimeout.sock_read (q.v.) for download-connections.",
        min_value=0.0,
    )

    def validate_url(self, value):
        """
        Check if the 'url' is a ``file://`` path, and if so, ensure it's an ALLOWED_IMPORT_PATH.

        The ALLOWED_IMPORT_PATH is specified as a Pulp setting.

        Args:
            value: The user-provided value for 'url' to be validated.

        Raises:
            ValidationError: When the url starts with `file://`, but is not a subfolder of a path in
                the ALLOWED_IMPORT_PATH setting.

        Returns:
            The validated value.
        """
        if not value.lower().startswith("file://"):
            return value

        user_path = value[7:]

        for allowed_path in settings.ALLOWED_IMPORT_PATHS:
            user_provided_realpath = os.path.realpath(user_path)
            if user_provided_realpath.startswith(allowed_path):
                return value
        raise serializers.ValidationError(_("url '{}' is not an allowed import path").format(value))

    class Meta:
        abstract = True
        model = models.Remote
        fields = ModelSerializer.Meta.fields + (
            "name",
            "url",
            "ca_cert",
            "client_cert",
            "client_key",
            "tls_validation",
            "proxy_url",
            "username",
            "password",
            "pulp_last_updated",
            "download_concurrency",
            "policy",
            "total_timeout",
            "connect_timeout",
            "sock_connect_timeout",
            "sock_read_timeout",
        )


class RepositorySyncURLSerializer(ValidateFieldsMixin, serializers.Serializer):
    remote = DetailRelatedField(
        required=False,
        view_name_pattern=r"remotes(-.*/.*)-detail",
        queryset=models.Remote.objects.all(),
        help_text=_("A remote to sync from. This will override a remote set on repository."),
    )

    mirror = fields.BooleanField(
        required=False,
        default=False,
        help_text=_(
            "If ``True``, synchronization will remove all content that is not present in "
            "the remote repository. If ``False``, sync will be additive only."
        ),
    )

    def validate(self, data):
        data = super().validate(data)

        try:
            remote = models.Repository.objects.get(pk=self.context["repository_pk"]).remote
        except KeyError:
            remote = None

        if "remote" not in data and not remote:
            raise serializers.ValidationError(
                {"remote": _("This field is required since a remote is not set on the repository.")}
            )

        return data


class ContentSummarySerializer(serializers.Serializer):
    """
    Serializer for the RepositoryVersion content summary
    """

    def to_representation(self, obj):
        """
        The summary of contained content.

        Returns:
            dict: The dictionary has the following format.::

                {
                    'added': {<pulp_type>: {'count': <count>, 'href': <href>},
                    'removed': {<pulp_type>: {'count': <count>, 'href': <href>},
                    'present': {<pulp_type>: {'count': <count>, 'href': <href>},
                }

        """
        to_return = {"added": {}, "removed": {}, "present": {}}
        for count_detail in obj.counts.all():
            count_type = count_detail.get_count_type_display()
            item_dict = {"count": count_detail.count, "href": count_detail.content_href}
            to_return[count_type][count_detail.content_type] = item_dict

        return to_return

    def to_internal_value(self, data):
        """
        Setting the internal value.
        """
        return {
            self.added: data["added"],
            self.removed: data["removed"],
            self.present: data["present"],
        }

    added = serializers.DictField(child=serializers.DictField())

    removed = serializers.DictField(child=serializers.DictField())

    present = serializers.DictField(child=serializers.DictField())


class RepositoryVersionSerializer(ModelSerializer, NestedHyperlinkedModelSerializer):
    pulp_href = RepositoryVersionIdentityField()
    number = serializers.IntegerField(read_only=True)
    base_version = RepositoryVersionRelatedField(
        required=False,
        help_text=_(
            "A repository version whose content was used as the initial set of content "
            "for this repository version"
        ),
    )
    content_summary = ContentSummarySerializer(
        help_text=_(
            "Various count summaries of the content in the version and the HREF to view " "them."
        ),
        source="*",
        read_only=True,
    )

    class Meta:
        model = models.RepositoryVersion
        fields = ModelSerializer.Meta.fields + (
            "pulp_href",
            "number",
            "base_version",
            "content_summary",
        )


class RepositoryAddRemoveContentSerializer(ModelSerializer, NestedHyperlinkedModelSerializer):
    add_content_units = serializers.ListField(
        help_text=_(
            "A list of content units to add to a new repository version. This content is "
            "added after remove_content_units are removed."
        ),
        required=False,
    )
    remove_content_units = serializers.ListField(
        help_text=_(
            "A list of content units to remove from the latest repository version. "
            "You may also specify '*' as an entry to remove all content. This content is "
            "removed before add_content_units are added."
        ),
        required=False,
    )
    base_version = RepositoryVersionRelatedField(
        required=False,
        help_text=_(
            "A repository version whose content will be used as the initial set of content "
            "for the new repository version"
        ),
    )

    def validate_remove_content_units(self, value):
        if len(value) > 1 and "*" in value:
            raise serializers.ValidationError("Cannot supply content units and '*'.")
        return value

    class Meta:
        model = models.RepositoryVersion
        fields = ["add_content_units", "remove_content_units", "base_version"]
