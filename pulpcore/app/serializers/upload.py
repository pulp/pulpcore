import re

from gettext import gettext as _
from rest_framework import serializers

from pulpcore.app import models
from pulpcore.app.serializers import base, ValidateFieldsMixin


CONTENT_RANGE_PATTERN = r"^bytes (\d+)-(\d+)/(\d+|[*])$"


class UploadChunkSerializer(ValidateFieldsMixin, serializers.Serializer):
    file = serializers.FileField(help_text=_("A chunk of the uploaded file."), write_only=True)

    sha256 = serializers.CharField(
        help_text=_("The SHA-256 checksum of the chunk if available."),
        required=False,
        allow_null=True,
        write_only=True,
    )

    offset = serializers.IntegerField(read_only=True)

    size = serializers.IntegerField(read_only=True)

    def validate(self, data):
        data = super().validate(data)

        content_range = self.context["request"].META.get("HTTP_CONTENT_RANGE", "")
        match = re.compile(CONTENT_RANGE_PATTERN).match(content_range)
        if not match:
            raise serializers.ValidationError(_("Invalid or missing content range header."))
        data["start"] = start = int(match[1])
        end = int(match[2])

        if (end - start + 1) != len(data["file"]):
            raise serializers.ValidationError(_("Chunk size does not match content range."))

        if end > self.context["upload"].size - 1:
            raise serializers.ValidationError(_("End byte is greater than upload size."))

        return data

    class Meta:
        model = models.UploadChunk
        fields = ("file", "sha256", "offset", "size")


class UploadSerializer(base.ModelSerializer):
    """Serializer for chunked uploads."""

    pulp_href = base.IdentityField(view_name="uploads-detail")

    size = serializers.IntegerField(help_text=_("The size of the upload in bytes."))

    completed = serializers.DateTimeField(
        help_text=_("Timestamp when upload is committed."), read_only=True
    )

    class Meta:
        model = models.Upload
        fields = base.ModelSerializer.Meta.fields + ("size", "completed")


class UploadDetailSerializer(UploadSerializer):
    chunks = UploadChunkSerializer(many=True, read_only=True)

    class Meta(UploadSerializer.Meta):
        fields = UploadSerializer.Meta.fields + ("chunks",)


class UploadCommitSerializer(ValidateFieldsMixin, serializers.Serializer):
    sha256 = serializers.CharField(help_text=_("The expected sha256 checksum for the file."))
