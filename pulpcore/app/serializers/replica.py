from gettext import gettext as _

from rest_framework import serializers
from rest_framework.validators import UniqueValidator

from pulpcore.app.serializers import HiddenFieldsMixin
from pulpcore.app.serializers import (
    IdentityField,
    ModelSerializer,
)


from pulpcore.app.models import UpstreamPulp


class UpstreamPulpSerializer(ModelSerializer, HiddenFieldsMixin):
    """
    Serializer for a Server.
    """

    pulp_href = IdentityField(view_name="upstream-pulps-detail")
    name = serializers.CharField(
        help_text=_("A unique name for this Pulp server."),
        validators=[UniqueValidator(queryset=UpstreamPulp.objects.all())],
    )
    base_url = serializers.CharField(
        help_text="The transport, hostname, and an optional port of the Pulp server. e.g. "
        "https://example.com"
    )
    api_root = serializers.CharField(help_text="The API root. Defaults to '/pulp/'.")
    domain = serializers.CharField(
        help_text=_("The domain of the Pulp server if enabled."),
        required=False,
        allow_null=True,
    )
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
        write_only=True,
    )
    tls_validation = serializers.BooleanField(
        help_text="If True, TLS peer validation must be performed.", required=False
    )

    username = serializers.CharField(
        help_text="The username to be used for authentication when syncing.",
        required=False,
        allow_null=True,
        write_only=True,
    )
    password = serializers.CharField(
        help_text=_(
            "The password to be used for authentication when syncing. Extra leading and trailing "
            "whitespace characters are not trimmed."
        ),
        required=False,
        allow_null=True,
        write_only=True,
        trim_whitespace=False,
        style={"input_type": "password"},
    )
    pulp_last_updated = serializers.DateTimeField(
        help_text="Timestamp of the most recent update of the remote.", read_only=True
    )

    pulp_label_select = serializers.CharField(
        help_text=_(
            "One or more comma separated labels that will be used to filter distributions on the "
            'upstream Pulp. E.g. "foo=bar,key=val" or "foo,key"'
        ),
        allow_null=True,
        allow_blank=True,
        required=False,
    )

    last_replication = serializers.DateTimeField(
        help_text=_(
            "Timestamp of the last replication that occurred. Equals to 'null' if no "
            "replication task has been executed."
        ),
        read_only=True,
    )

    class Meta:
        abstract = True
        model = UpstreamPulp
        fields = ModelSerializer.Meta.fields + (
            "name",
            "base_url",
            "api_root",
            "domain",
            "ca_cert",
            "client_cert",
            "client_key",
            "tls_validation",
            "username",
            "password",
            "pulp_last_updated",
            "hidden_fields",
            "pulp_label_select",
            "last_replication",
        )
