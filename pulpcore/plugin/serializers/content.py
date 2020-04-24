from gettext import gettext as _

from logging import getLogger

from rest_framework.serializers import (
    FileField,
    Serializer,
    ValidationError,
)
from pulpcore.plugin.models import Artifact, Repository
from pulpcore.plugin.serializers import (
    DetailRelatedField,
    NoArtifactContentSerializer,
    SingleArtifactContentSerializer,
)


log = getLogger(__name__)


class UploadSerializerFieldsMixin(Serializer):
    """A mixin class that contains fields and methods common to content upload serializers."""

    file = FileField(
        help_text=_("An uploaded file that may be turned into the artifact of the content unit."),
        required=False,
        write_only=True,
    )
    repository = DetailRelatedField(
        help_text=_("A URI of a repository the new content unit should be associated with."),
        required=False,
        write_only=True,
        view_name_pattern=r"repositories(-.*/.*)-detail",
        queryset=Repository.objects.all(),
    )

    def create(self, validated_data):
        """
        Save a GenericContent unit.

        This must be used inside a task that locks on the Artifact and if given, the repository.
        """

        repository = validated_data.pop("repository", None)
        content = super().create(validated_data)

        if repository:
            repository.cast()
            content_to_add = self.Meta.model.objects.filter(pk=content.pk)

            # create new repo version with uploaded package
            with repository.new_version() as new_version:
                new_version.add_content(content_to_add)
        return content

    class Meta:
        fields = ("file", "repository")


class NoArtifactContentUploadSerializer(UploadSerializerFieldsMixin, NoArtifactContentSerializer):
    """A serializer for content types with no Artifact."""

    def create(self, validated_data):
        """Create a new content and remove the already parsed file from validated_data."""
        validated_data.pop("file", None)
        return super().create(validated_data)

    class Meta:
        fields = NoArtifactContentSerializer.Meta.fields + UploadSerializerFieldsMixin.Meta.fields


class SingleArtifactContentUploadSerializer(
    UploadSerializerFieldsMixin, SingleArtifactContentSerializer
):
    """
    A serializer for content_types with a single Artifact.

    The Artifact can either be specified via it's url, or a new file can be uploaded.
    Additionally a repository can be specified, to which the content unit will be added.

    When using this serializer, the creation of the real content must be wrapped in a task that
    locks the Artifact and when specified, the repository.
    """

    def __init__(self, *args, **kwargs):
        """Initializer for SingleArtifactContentUploadSerializer."""
        super().__init__(*args, **kwargs)
        if self.fields.get("artifact"):
            self.fields["artifact"].required = False

    def validate(self, data):
        """Validate that we have an Artifact or can create one."""

        data = super().validate(data)

        if "file" in data:
            if "artifact" in data:
                raise ValidationError(_("Only one of 'file' and 'artifact' may be specified."))
            data["artifact"] = Artifact.init_and_validate(data.pop("file"))
        elif "artifact" not in data:
            raise ValidationError(_("One of 'file' and 'artifact' must be specified."))

        if "request" not in self.context:
            data = self.deferred_validate(data)

        return data

    def deferred_validate(self, data):
        """
        Validate the content unit by deeply analyzing the specified Artifact.

        This is only called when validating without a request context to prevent stalling
        an ongoing http request.
        It should be overwritten by plugins to extract metadata from the actual content in
        much the same way as `validate`.
        """
        return data

    class Meta(SingleArtifactContentSerializer.Meta):
        fields = (
            SingleArtifactContentSerializer.Meta.fields + UploadSerializerFieldsMixin.Meta.fields
        )
