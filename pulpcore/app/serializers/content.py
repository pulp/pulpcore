from gettext import gettext as _
import hashlib

from django.conf import settings
from django.db import transaction
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


class ContentChecksumSerializer(serializers.Serializer):
    """
    Provide a serializer with artifact checksum fields for single artifact content.

    If you use this serializer, it's recommended that you prefetch artifacts:

        Content.objects.prefetch_related("_artifacts").all()
    """

    md5 = fields.ContentArtifactChecksumField(
        help_text=_("The MD5 checksum if available."),
        checksum='md5',
    )

    sha1 = fields.ContentArtifactChecksumField(
        help_text=_("The SHA-1 checksum if available."),
        checksum='sha1',
    )

    sha224 = fields.ContentArtifactChecksumField(
        help_text=_("The SHA-224 checksum if available."),
        checksum='sha224',
    )

    sha256 = fields.ContentArtifactChecksumField(
        help_text=_("The SHA-256 checksum if available."),
        checksum='sha256',
    )

    sha384 = fields.ContentArtifactChecksumField(
        help_text=_("The SHA-384 checksum if available."),
        checksum='sha384',
    )

    sha512 = fields.ContentArtifactChecksumField(
        help_text=_("The SHA-512 checksum if available."),
        checksum='sha512',
    )

    class Meta:
        model = models.Artifact
        fields = base.ModelSerializer.Meta.fields + ('md5', 'sha1', 'sha224', 'sha256', 'sha384',
                                                     'sha512')


class ArtifactSerializer(base.ModelSerializer):
    _href = base.IdentityField(
        view_name='artifacts-detail',
    )

    file = serializers.FileField(
        help_text=_("The stored file."),
        allow_empty_file=True,
        required=False
    )

    upload = serializers.HyperlinkedRelatedField(
        help_text=_("An href for an Upload."),
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
        allow_null=True,
    )

    sha1 = serializers.CharField(
        help_text=_("The SHA-1 checksum of the file if available."),
        required=False,
        allow_null=True,
    )

    sha224 = serializers.CharField(
        help_text=_("The SHA-224 checksum of the file if available."),
        required=False,
        allow_null=True,
    )

    sha256 = serializers.CharField(
        help_text=_("The SHA-256 checksum of the file if available."),
        required=False,
        allow_null=True,
    )

    sha384 = serializers.CharField(
        help_text=_("The SHA-384 checksum of the file if available."),
        required=False,
        allow_null=True,
    )

    sha512 = serializers.CharField(
        help_text=_("The SHA-512 checksum of the file if available."),
        required=False,
        allow_null=True,
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
    _href = base.IdentityField(
        view_name='upload-detail',
    )
    file = serializers.FileField(
        help_text=_("Uploaded file."),
        write_only=True,
    )

    class Meta:
        model = models.Upload
        fields = ('_href', 'offset', 'expires_at', 'file')


class UploadPUTSerializer(serializers.Serializer):
    """Serializer for starting chunked uploads."""
    file = serializers.FileField(
        help_text=_("A chunk of a file to upload."),
        write_only=True,
        required=True
    )


class UploadFinishSerializer(serializers.Serializer):
    """Serializer for POST to complete Upload and validate Upload's sha256 checksum"""
    if settings.DRF_CHUNKED_UPLOAD_CHECKSUM == 'md5':
        md5 = serializers.CharField(
            help_text=_("The expected md5 hex digest of the file."),
            required=True,
            allow_blank=False,
            write_only=True,
        )
    elif settings.DRF_CHUNKED_UPLOAD_CHECKSUM == 'sha256':
        sha256 = serializers.CharField(
            help_text=_("The expected sha256 hex digest of the file."),
            required=True,
            allow_blank=False,
            write_only=True,
        )


class UploadPOSTSerializer(base.ModelSerializer, UploadFinishSerializer):
    """Serializer for creating chunked uploads from entire file."""
    file = serializers.FileField(
        help_text=_("The full file to upload."),
        required=True
    )

    class Meta:
        model = models.Upload
        fields = ['file', settings.DRF_CHUNKED_UPLOAD_CHECKSUM]


