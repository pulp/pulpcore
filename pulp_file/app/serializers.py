from gettext import gettext as _

from rest_framework import serializers

from pulpcore.plugin import models
from pulpcore.plugin.serializers import (
    AlternateContentSourceSerializer,
    ContentChecksumSerializer,
    DetailRelatedField,
    DistributionSerializer,
    PublicationSerializer,
    RemoteSerializer,
    RepositorySerializer,
    SingleArtifactContentUploadSerializer,
)
from pulpcore.plugin.util import get_domain_pk

from pulp_file.app.models import (
    FileAlternateContentSource,
    FileContent,
    FileDistribution,
    FileRemote,
    FileRepository,
    FilePublication,
)


class FileContentSerializer(SingleArtifactContentUploadSerializer, ContentChecksumSerializer):
    """
    Serializer for File Content.
    """

    def deferred_validate(self, data):
        """Validate the FileContent data."""
        data = super().deferred_validate(data)

        data["digest"] = data["artifact"].sha256

        return data

    def retrieve(self, validated_data):
        content = FileContent.objects.filter(
            digest=validated_data["digest"],
            relative_path=validated_data["relative_path"],
            pulp_domain=get_domain_pk(),
        )
        return content.first()

    class Meta:
        fields = (
            SingleArtifactContentUploadSerializer.Meta.fields
            + ContentChecksumSerializer.Meta.fields
        )
        model = FileContent


class FileRepositorySerializer(RepositorySerializer):
    """
    Serializer for File Repositories.
    """

    autopublish = serializers.BooleanField(
        help_text=_(
            "Whether to automatically create publications for new repository versions, "
            "and update any distributions pointing to this repository."
        ),
        default=False,
        required=False,
    )

    manifest = serializers.CharField(
        help_text=_("Filename to use for manifest file containing metadata for all the files."),
        default="PULP_MANIFEST",
        required=False,
        allow_null=True,
    )

    class Meta:
        fields = RepositorySerializer.Meta.fields + ("autopublish", "manifest")
        model = FileRepository


class FileRemoteSerializer(RemoteSerializer):
    """
    Serializer for File Remotes.
    """

    policy = serializers.ChoiceField(
        help_text="The policy to use when downloading content. The possible values include: "
        "'immediate', 'on_demand', and 'streamed'. 'immediate' is the default.",
        choices=models.Remote.POLICY_CHOICES,
        default=models.Remote.IMMEDIATE,
    )

    class Meta:
        fields = RemoteSerializer.Meta.fields
        model = FileRemote


class FilePublicationSerializer(PublicationSerializer):
    """
    Serializer for File Publications.
    """

    distributions = DetailRelatedField(
        help_text=_("This publication is currently hosted as defined by these distributions."),
        source="distribution_set",
        view_name="filedistributions-detail",
        many=True,
        read_only=True,
    )
    manifest = serializers.CharField(
        help_text=_("Filename to use for manifest file containing metadata for all the files."),
        default="PULP_MANIFEST",
        required=False,
        allow_null=True,
    )

    class Meta:
        model = FilePublication
        fields = PublicationSerializer.Meta.fields + ("distributions", "manifest")


class FileDistributionSerializer(DistributionSerializer):
    """
    Serializer for File Distributions.
    """

    publication = DetailRelatedField(
        required=False,
        help_text=_("Publication to be served"),
        view_name_pattern=r"publications(-.*/.*)?-detail",
        queryset=models.Publication.objects.exclude(complete=False),
        allow_null=True,
    )

    class Meta:
        fields = DistributionSerializer.Meta.fields + ("publication",)
        model = FileDistribution


class FileAlternateContentSourceSerializer(AlternateContentSourceSerializer):
    """
    Serializer for File alternate content source.
    """

    def validate_paths(self, paths):
        """Validate that paths do not start with /."""
        for path in paths:
            if path.startswith("/"):
                raise serializers.ValidationError(_("Path cannot start with a slash."))
        return paths

    class Meta:
        fields = AlternateContentSourceSerializer.Meta.fields
        model = FileAlternateContentSource
