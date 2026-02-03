import json
from gettext import gettext as _
from tempfile import NamedTemporaryFile
from urllib.parse import urlparse

from django.db import DatabaseError
from rest_framework.serializers import (
    CharField,
    FileField,
    ValidationError,
    Serializer,
)

from pulpcore.app.files import PulpTemporaryUploadedFile
from pulpcore.app.models import Artifact, PulpTemporaryFile, Remote, Upload, UploadChunk
from pulpcore.app.serializers import (
    RelatedField,
    ArtifactSerializer,
    NoArtifactContentSerializer,
    SingleArtifactContentSerializer,
)
from pulpcore.app.serializers.base import RemoteNetworkConfigSerializer
from pulpcore.app.util import get_domain_pk


class UploadSerializerFieldsMixin(Serializer):
    """A mixin class that contains fields and methods common to content upload serializers."""

    REMOTE_CLASS = Remote

    file = FileField(
        help_text=_("An uploaded file that may be turned into the content unit."),
        required=False,
        write_only=True,
    )
    upload = RelatedField(
        help_text=_("An uncommitted upload that may be turned into the content unit."),
        required=False,
        write_only=True,
        view_name=r"uploads-detail",
        queryset=Upload.objects.all(),
    )
    file_url = CharField(
        help_text=_("A url that Pulp can download and turn into the content unit."),
        required=False,
        write_only=True,
    )

    downloader_config = RemoteNetworkConfigSerializer(
        help_text=_(
            "Configuration for the download process (e.g., proxies, auth, timeouts). "
            "Only applicable when providing a 'file_url."
        ),
        required=False,
        write_only=True,
    )

    def validate_file_url(self, value):
        """Parse out the auth if provided."""
        url_parse = urlparse(value)
        if url_parse.username or url_parse.password:
            kwargs = {"username": url_parse.username, "password": url_parse.password}
            if self.context.get("remote_kwargs"):
                self.context["remote_kwargs"].update(kwargs)
            else:
                self.context["remote_kwargs"] = kwargs

        return url_parse._replace(netloc=url_parse.netloc.split("@")[-1]).geturl()

    def download(self, url, expected_digests=None, expected_size=None):
        """
        Downloads & returns the file from the url.

        Plugins can overwrite this method on their content serializers to get specific download
        behavior for their content types.

        Args:
            url (str): A url that Pulp can download
            expected_digests (dict): A dict of expected digests.
            expected_size (int): The expected size in bytes.

        Returns:
            PulpTemporaryUploadedFile: the downloaded file
        """
        remote = self.REMOTE_CLASS(url=url, **self.context.get("remote_kwargs"))
        downloader = remote.get_downloader(
            url=url, expected_digests=expected_digests, expected_size=expected_size
        )
        result = downloader.fetch()
        return PulpTemporaryUploadedFile.from_file(open(result.path, "rb"))

    def validate(self, data):
        """Validate that we have an Artifact/File or can create one."""

        data = super().validate(data)
        downloader_config = data.pop("downloader_config", {})
        if self.context.get("remote_kwargs") is None:
            self.context["remote_kwargs"] = downloader_config
        else:
            self.context["remote_kwargs"].update(downloader_config)

        if self.context.get("request") is not None:
            upload_fields = {
                field
                for field in self.Meta.fields
                if field in {"file", "upload", "artifact", "file_url"}
            }
            if len(upload_fields.intersection(data.keys())) != 1:
                raise ValidationError(
                    _("Exactly one of {} must be specified.").format(", ".join(upload_fields))
                )
        else:
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
        if upload := data.pop("upload", None):
            self.context["upload"] = upload
            chunks = UploadChunk.objects.filter(upload=upload).order_by("offset")
            with NamedTemporaryFile(mode="ab", dir=".", delete=False) as temp_file:
                for chunk in chunks:
                    temp_file.write(chunk.file.read())
                    chunk.file.close()
                temp_file.flush()
            data["file"] = PulpTemporaryUploadedFile.from_file(open(temp_file.name, "rb"))
        elif pulp_temp_file_pk := self.context.get("pulp_temp_file_pk"):
            pulp_temp_file = PulpTemporaryFile.objects.get(pk=pulp_temp_file_pk)
            data["file"] = PulpTemporaryUploadedFile.from_file(pulp_temp_file.file)
        elif file_url := data.pop("file_url", None):
            expected_digests = data.get("expected_digests", None)
            expected_size = data.get("expected_size", None)
            data["file"] = self.download(
                file_url, expected_digests=expected_digests, expected_size=expected_size
            )
        return data

    def create(self, validated_data):
        result = super().create(validated_data)
        if upload := self.context.get("upload"):
            upload.delete()
        if pulp_temp_file_pk := self.context.get("pulp_temp_file_pk"):
            pulp_temp_file = PulpTemporaryFile.objects.get(pk=pulp_temp_file_pk)
            pulp_temp_file.delete()
        return result

    class Meta:
        fields = ("file", "upload", "file_url", "downloader_config")


class NoArtifactContentUploadSerializer(UploadSerializerFieldsMixin, NoArtifactContentSerializer):
    """A serializer for content types with no Artifact."""

    def deferred_validate(self, data):
        """Ensure file is present in validated_data."""
        data = super().deferred_validate(data)
        if "file" not in data:
            if "artifact" in data:
                artifact = data.pop("artifact")
                with NamedTemporaryFile(mode="ab", dir=".", delete=False) as temp_file:
                    temp_file.write(artifact.file.read())
                    temp_file.flush()
                data["file"] = PulpTemporaryUploadedFile.from_file(open(temp_file.name, "rb"))
            else:
                raise RuntimeError("No file found for NoArtifactContentUploadSerializer.")
        return data

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

    def __init__(self, *args, **kwargs):
        """Initializer for SingleArtifactContentUploadSerializer."""
        # pulp_labels can come into the system as a str-of-json - intercept and correct
        # before attempting to validate
        if (
            "data" in kwargs
            and "pulp_labels" in kwargs["data"]
            and isinstance(kwargs["data"]["pulp_labels"], str)
        ):
            try:
                kwargs["data"]["pulp_labels"] = json.loads(kwargs["data"]["pulp_labels"])
            except AttributeError:
                # malformed uploads cause request.data._mutable=False and pulp_labels will fail
                # to be modified with "AttributeError: This QueryDict instance is immutable".
                pass

        super().__init__(*args, **kwargs)

        if "artifact" in self.fields:
            self.fields["artifact"].required = False

    def validate(self, data):
        """
        Validate the serializer data, with special handling for pulp_labels deserialization.

        This method checks if pulp_labels failed to be deserialized from JSON string to dict
        during initialization (typically due to immutable QueryDict).
        """
        if "pulp_labels" in data and isinstance(data["pulp_labels"], str):
            raise ValidationError(
                _(
                    """
                    Failed to deserialize pulp_labels!
                    This error often occurs when file didn't upload, is incomplete, or
                    when pulp_labels are not in a valid JSON format.
                    """
                )
            )
        return super().validate(data)

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
        data = super().deferred_validate(data)

        if "file" in data:
            file = data.pop("file")
            # if artifact already exists, let's use it
            try:
                artifact = Artifact.objects.get(
                    sha256=file.hashers["sha256"].hexdigest(),
                    pulp_domain=get_domain_pk(),
                )
                if not artifact.pulp_domain.get_storage().exists(artifact.file.name):
                    artifact.file = file
                    artifact.save()
                else:
                    artifact.touch()
            except (Artifact.DoesNotExist, DatabaseError):
                artifact_data = {"file": file}
                serializer = ArtifactSerializer(data=artifact_data)
                serializer.is_valid(raise_exception=True)
                artifact = serializer.save()
            data["artifact"] = artifact
        return data

    class Meta(SingleArtifactContentSerializer.Meta):
        fields = (
            SingleArtifactContentSerializer.Meta.fields + UploadSerializerFieldsMixin.Meta.fields
        )
