from gettext import gettext as _
import hashlib

from django.db import transaction
from drf_chunked_upload.serializers import ChunkedUploadSerializer
from rest_framework import serializers
from rest_framework.validators import UniqueValidator

from pulpcore.app import models, files
from pulpcore.app.serializers import base, fields


UNIQUE_ALGORITHMS = ['sha256', 'sha384', 'sha512']


class BaseContentSerializer(base.MasterModelSerializer):
    _href = base.DetailIdentityField()

    class Meta:
        model = models.Content
        fields = base.MasterModelSerializer.Meta.fields


class NoArtifactContentSerializer(BaseContentSerializer):

    class Meta:
        model = models.Content
        fields = BaseContentSerializer.Meta.fields


class SingleArtifactContentSerializer(BaseContentSerializer):
    _artifact = fields.SingleContentArtifactField(
        help_text=_("Artifact file representing the physical content"),
    )

    _relative_path = serializers.CharField(
        help_text=_("Path where the artifact is located relative to distributions base_path"),
        validators=[fields.relative_path_validator],
        write_only=True,
    )

    @transaction.atomic
    def create(self, validated_data):
        """
        Create the content and associate it with its Artifact.

        Args:
            validated_data (dict): Data to save to the database
        """
        artifact = validated_data.pop('_artifact')
        relative_path = validated_data.pop('_relative_path')
        content = self.Meta.model.objects.create(**validated_data)
        models.ContentArtifact.objects.create(
            artifact=artifact,
            content=content,
            relative_path=relative_path,
        )
        return content

    class Meta:
        model = models.Content
        fields = BaseContentSerializer.Meta.fields + ('_artifact', '_relative_path')


class MultipleArtifactContentSerializer(BaseContentSerializer):
    _artifacts = fields.ContentArtifactsField(
        help_text=_("A dict mapping relative paths inside the Content to the corresponding"
                    "Artifact URLs. E.g.: {'relative/path': "
                    "'/artifacts/1/'"),
    )

    @transaction.atomic
    def create(self, validated_data):
        """
        Create the content and associate it with all its Artifacts.

        Args:
            validated_data (dict): Data to save to the database
        """
        _artifacts = validated_data.pop('_artifacts')
        content = self.Meta.model.objects.create(**validated_data)
        for relative_path, artifact in _artifacts.items():
            models.ContentArtifact.objects.create(
                artifact=artifact,
                content=content,
                relative_path=relative_path,
            )
        return content

    class Meta:
        model = models.Content
        fields = BaseContentSerializer.Meta.fields + ('_artifacts',)


class ArtifactSerializer(base.ModelSerializer):
    _href = base.IdentityField(
        view_name='artifacts-detail',
    )

    file = serializers.FileField(
        help_text=_("The stored file."),
        required=False
    )

    upload = serializers.HyperlinkedRelatedField(
        view_name="upload-detail",
        write_only=True,
        required=False,
        queryset=models.Upload.objects.filter(status=models.Upload.COMPLETE)
    )

    size = serializers.IntegerField(
        help_text=_("The size of the file in bytes."),
        required=False
    )

    md5 = serializers.CharField(
        help_text=_("The MD5 checksum of the file if available."),
        required=False,
        allow_blank=True
    )

    sha1 = serializers.CharField(
        help_text=_("The SHA-1 checksum of the file if available."),
        required=False,
        allow_blank=True
    )

    sha224 = serializers.CharField(
        help_text=_("The SHA-224 checksum of the file if available."),
        required=False,
        allow_blank=True
    )

    sha256 = serializers.CharField(
        help_text=_("The SHA-256 checksum of the file if available."),
        required=False,
        allow_blank=True
    )

    sha384 = serializers.CharField(
        help_text=_("The SHA-384 checksum of the file if available."),
        required=False,
        allow_blank=True
    )

    sha512 = serializers.CharField(
        help_text=_("The SHA-512 checksum of the file if available."),
        required=False,
        allow_blank=True
    )

    def validate(self, data):
        """
        Validate file by size and by all checksums provided.

        Args:
            data (:class:`django.http.QueryDict`): QueryDict mapping Artifact model fields to their
                values

        Raises:
            :class:`rest_framework.exceptions.ValidationError`: When the expected file size or any
                of the checksums don't match their actual values.
        """
        super().validate(data)

        if ('file' not in data and 'upload' not in data) or \
                ('file' in data and 'upload' in data):
            raise serializers.ValidationError(_("Either 'file' or 'upload' parameter must be "
                                                "supplied but not both."))

        if 'upload' in data:
            self.upload = data.pop('upload')
            data['file'] = files.PulpTemporaryUploadedFile.from_file(self.upload.file.file)

        if 'size' in data:
            if data['file'].size != int(data['size']):
                raise serializers.ValidationError(_("The size did not match actual size of file."))
        else:
            data['size'] = data['file'].size

        for algorithm in hashlib.algorithms_guaranteed:
            if algorithm in models.Artifact.DIGEST_FIELDS:
                digest = data['file'].hashers[algorithm].hexdigest()

                if algorithm in data and digest != data[algorithm]:
                    raise serializers.ValidationError(_("The %s checksum did not match.")
                                                      % algorithm)
                else:
                    data[algorithm] = digest
                if algorithm in UNIQUE_ALGORITHMS:
                    validator = UniqueValidator(models.Artifact.objects.all(),
                                                message=_("{0} checksum must be "
                                                          "unique.").format(algorithm))
                    validator.field_name = algorithm
                    validator.instance = None
                    validator(digest)
        return data

    def create(self, validated_data):
        """
        Create the artifact and delete its associated upload (if there is one)

        Args:
            validated_data (dict): Data to save to the database
        """
        artifact = super().create(validated_data)
        if hasattr(self, 'upload'):
            # creating an artifact will move the upload file so we need to delete the db record
            self.upload.delete()
        return artifact

    class Meta:
        model = models.Artifact
        fields = base.ModelSerializer.Meta.fields + ('file', 'size', 'md5', 'sha1', 'sha224',
                                                     'sha256', 'sha384', 'sha512', 'upload')


class UploadSerializer(base.ModelSerializer):
    """Serializer for chunked uploads."""
    viewname = 'uploads:upload-detail'

    _href = base.IdentityField(
        view_name='upload-detail',
    )

    file = serializers.FileField(
        write_only=True,
    )

    class Meta(ChunkedUploadSerializer.Meta):
        model = models.Upload
        fields = ('_href', 'file', 'offset', 'expires_at')
