from gettext import gettext as _
from rest_framework import serializers

from pulpcore.app import models
from pulpcore.app.serializers import base


class UploadSerializer(base.ModelSerializer):
    """Serializer for chunked uploads."""
    _href = base.IdentityField(
        view_name='uploads-detail',
    )

    size = serializers.IntegerField(
        help_text=_("The size of the upload in bytes.")
    )

    completed = serializers.DateTimeField(
        help_text=_("Timestamp when upload is committed."),
        read_only=True
    )

    class Meta:
        model = models.Upload
        fields = base.ModelSerializer.Meta.fields + ('size', 'completed')


class UploadChunkSerializer(serializers.Serializer):
    file = serializers.FileField(
        help_text=_("A chunk of the uploaded file."),
    )


class UploadCommitSerializer(serializers.Serializer):
    sha256 = serializers.CharField(
        help_text=_("The expected sha256 checksum for the file.")
    )
