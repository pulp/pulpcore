from gettext import gettext as _

from logging import getLogger
from tempfile import NamedTemporaryFile

from django.db import DatabaseError
from rest_framework.serializers import (
    FileField,
    Serializer,
    ValidationError,
)
from pulpcore.app.files import PulpTemporaryUploadedFile
from pulpcore.app.models import Artifact, Repository, Upload, UploadChunk
from pulpcore.app.serializers import (
    DetailRelatedField,
    RelatedField,
    ArtifactSerializer,
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

    The Artifact can either be specified via it's url or an uncommitted upload, or a new file can
    be uploaded in the POST data.
    Additionally a repository can be specified, to which the content unit will be added.

    When using this serializer, the creation of the real content must be wrapped in a task that
    touches the Artifact and locks the Upload and Repository when specified.
    """

    upload = RelatedField(
        help_text=_(
            "An uncommitted upload that may be turned into the artifact of the content unit."
        ),
        required=False,
        write_only=True,
        view_name=r"uploads-detail",
        queryset=Upload.objects.all(),
    )

    def __init__(self, *args, **kwargs):
        """Initializer for SingleArtifactContentUploadSerializer."""
        super().__init__(*args, **kwargs)
        if self.fields.get("artifact"):
            self.fields["artifact"].required = False

    def validate(self, data):
        """Validate that we have an Artifact or can create one."""

        data = super().validate(data)

        if len({"file", "upload", "artifact"}.intersection(data.keys())) != 1:
            raise ValidationError(
                _("Exactly one of 'file', 'artifact' or 'upload' must be specified.")
            )

        if "request" not in self.context:
            if "file" in data:
                raise RuntimeError(
                    "The file field must be resolved into an artifact by the viewset before "
                    "dispatching the create task."
                )
            data = self.deferred_validate(data)

        return data

    def deferred_validate(self, data):
        """
        Validate the content unit by deeply analyzing the specified Artifact.

        This is only called when validating without a request context to prevent stalling
        an ongoing http request.
        It should be overwritten by plugins to extract metadata from the actual content in
        much the same way as `validate`.
        When overwriting, plugins must super-call this method to handle uploads before analyzing
        the artifact.
        """
        if "upload" in data:
            upload = data.pop("upload")
            self.context["upload"] = upload
            chunks = UploadChunk.objects.filter(upload=upload).order_by("offset")
            with NamedTemporaryFile(mode="ab", dir=".", delete=False) as temp_file:
                for chunk in chunks:
                    temp_file.write(chunk.file.read())
                    chunk.file.close()
                temp_file.flush()
            with open(temp_file.name, "rb") as artifact_file:
                file = PulpTemporaryUploadedFile.from_file(artifact_file)
                # if artifact already exists, let's use it
                try:
                    artifact = Artifact.objects.get(sha256=file.hashers["sha256"].hexdigest())
                    artifact.touch()
                except (Artifact.DoesNotExist, DatabaseError):
                    artifact_data = {"file": file}
                    serializer = ArtifactSerializer(data=artifact_data)
                    serializer.is_valid(raise_exception=True)
                    artifact = serializer.save()
            data["artifact"] = artifact
        return data

    def create(self, validated_data):
        result = super().create(validated_data)
        if upload := self.context.get("upload"):
            upload.delete()
        return result

    class Meta(SingleArtifactContentSerializer.Meta):
        fields = (
            SingleArtifactContentSerializer.Meta.fields
            + UploadSerializerFieldsMixin.Meta.fields
            + ("upload",)
        )
