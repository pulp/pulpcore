from gettext import gettext as _

from django.db import transaction, IntegrityError
from rest_framework import serializers
from rest_framework.validators import UniqueValidator

from pulpcore.app import models
from pulpcore.app.serializers import base, fields, DetailRelatedField
from pulpcore.app.util import get_domain


class NoArtifactContentSerializer(base.ModelSerializer):
    pulp_href = base.DetailIdentityField(view_name_pattern=r"contents(-.*/.*)-detail")
    repository = DetailRelatedField(
        help_text=_("A URI of a repository the new content unit should be associated with."),
        required=False,
        write_only=True,
        view_name_pattern=r"repositories(-.*/.*)-detail",
        queryset=models.Repository.objects.all(),
    )

    def get_artifacts(self, validated_data):
        """
        Extract artifacts from validated_data.

        This function is supposed to extract the information about content artifacts from
        validated_data and return a dictionary with artifacts and relative paths as keys.
        """
        return {}

    def retrieve(self, validated_data):
        """
        Retrieve existing content unit if it exists, else return None.

        This method is plugin-specific and implementing it for a specific content type
        allows for uploading already existing content units of that type.
        """
        return None

    def validate(self, data):
        """Validate that we have an Artifact or can create one."""

        data = super().validate(data)
        if repository := data.get("repository"):
            if (
                self.Meta.model
                not in repository.get_model_for_pulp_type(repository.pulp_type).CONTENT_TYPES
            ):
                raise serializers.ValidationError("Content is not supported by this repository.")
        return data

    def create(self, validated_data):
        """
        Create the content and associate it with its Artifacts, or retrieve the existing content.

        Args:
            validated_data (dict): Data to save to the database
        """
        repository = validated_data.pop("repository", None)
        artifacts = self.get_artifacts(validated_data)

        content = self.retrieve(validated_data)
        if content is not None:
            content.touch()
        else:
            try:
                with transaction.atomic():
                    content = self.Meta.model.objects.create(**validated_data)
                    for relative_path, artifact in artifacts.items():
                        models.ContentArtifact.objects.create(
                            artifact=artifact, content=content, relative_path=relative_path
                        )
            except IntegrityError:
                content = self.retrieve(validated_data)
                if content is None:
                    raise

        if repository:
            repository.cast()
            content_to_add = self.Meta.model.objects.filter(pk=content.pk)

            # create new repo version with uploaded package
            with repository.new_version() as new_version:
                new_version.add_content(content_to_add)

        return content

    class Meta:
        model = models.Content
        fields = base.ModelSerializer.Meta.fields + ("repository",)


class SingleArtifactContentSerializer(NoArtifactContentSerializer):
    artifact = fields.SingleContentArtifactField(
        help_text=_("Artifact file representing the physical content"),
    )

    relative_path = serializers.CharField(
        help_text=_("Path where the artifact is located relative to distributions base_path"),
        validators=[fields.relative_path_validator],
        write_only=True,
    )

    def __init__(self, *args, **kwargs):
        """
        Initializer for SingleArtifactContentSerializer
        """
        super().__init__(*args, **kwargs)

        # If the content model has its own database field 'relative_path',
        # we should not mark the field write_only
        if hasattr(self.Meta.model, "relative_path") and "relative_path" in self.fields:
            self.fields["relative_path"].write_only = False

    def get_artifacts(self, validated_data):
        artifact = validated_data.pop("artifact")
        if "relative_path" not in self.fields or self.fields["relative_path"].write_only:
            relative_path = validated_data.pop("relative_path")
        else:
            relative_path = validated_data.get("relative_path")
        return {relative_path: artifact}

    class Meta:
        model = models.Content
        fields = NoArtifactContentSerializer.Meta.fields + ("artifact", "relative_path")


class MultipleArtifactContentSerializer(NoArtifactContentSerializer):
    artifacts = fields.ContentArtifactsField(
        help_text=_(
            "A dict mapping relative paths inside the Content to the corresponding"
            "Artifact URLs. E.g.: {'relative/path': "
            "'/artifacts/1/'"
        ),
    )

    def get_artifacts(self, validated_data):
        return validated_data.pop("artifacts")

    class Meta:
        model = models.Content
        fields = NoArtifactContentSerializer.Meta.fields + ("artifacts",)


class ContentChecksumSerializer(serializers.Serializer):
    """
    Provide a serializer with artifact checksum fields for single artifact content.

    If you use this serializer, it's recommended that you prefetch artifacts:

        Content.objects.prefetch_related("_artifacts").all()
    """

    md5 = fields.ContentArtifactChecksumField(
        help_text=_("The MD5 checksum if available."),
        checksum="md5",
    )

    sha1 = fields.ContentArtifactChecksumField(
        help_text=_("The SHA-1 checksum if available."),
        checksum="sha1",
    )

    sha224 = fields.ContentArtifactChecksumField(
        help_text=_("The SHA-224 checksum if available."),
        checksum="sha224",
    )

    sha256 = fields.ContentArtifactChecksumField(
        help_text=_("The SHA-256 checksum if available."),
        checksum="sha256",
    )

    sha384 = fields.ContentArtifactChecksumField(
        help_text=_("The SHA-384 checksum if available."),
        checksum="sha384",
    )

    sha512 = fields.ContentArtifactChecksumField(
        help_text=_("The SHA-512 checksum if available."),
        checksum="sha512",
    )

    class Meta:
        model = models.Content
        fields = base.ModelSerializer.Meta.fields + (
            "md5",
            "sha1",
            "sha224",
            "sha256",
            "sha384",
            "sha512",
        )


class ArtifactSerializer(base.ModelSerializer):
    pulp_href = base.IdentityField(view_name="artifacts-detail")

    file = serializers.FileField(help_text=_("The stored file."), allow_empty_file=True)

    size = serializers.IntegerField(help_text=_("The size of the file in bytes."), required=False)

    md5 = serializers.CharField(
        help_text=_("The MD5 checksum of the file if available."), required=False, allow_null=True
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
        if "size" in data:
            if data["file"].size != int(data["size"]):
                raise serializers.ValidationError(_("The size did not match actual size of file."))
        else:
            data["size"] = data["file"].size

        bad_algs = []
        for algorithm in models.Artifact.FORBIDDEN_DIGESTS:
            if algorithm in data:
                bad_algs.append(algorithm)
        if bad_algs:
            raise serializers.ValidationError(
                _("Checksum algorithms {} forbidden for this Pulp instance.").format(bad_algs)
            )

        for algorithm in reversed(models.Artifact.DIGEST_FIELDS):
            digest = data["file"].hashers[algorithm].hexdigest()

            if algorithm in data and digest != data[algorithm]:
                raise serializers.ValidationError(_("The %s checksum did not match.") % algorithm)
            else:
                data[algorithm] = digest

            if algorithm in models.Artifact.RELIABLE_DIGEST_FIELDS:
                validator = UniqueValidator(
                    models.Artifact.objects.filter(pulp_domain=get_domain()),
                    message=_("Artifact with {0} checksum of '{1}' already exists.").format(
                        algorithm, digest
                    ),
                )
                validator.instance = None
                validator(digest, self.fields[algorithm])

        return data

    class Meta:
        model = models.Artifact
        fields = base.ModelSerializer.Meta.fields + (
            "file",
            "size",
            "md5",
            "sha1",
            "sha224",
            "sha256",
            "sha384",
            "sha512",
        )


class SigningServiceSerializer(base.ModelSerializer):
    """
    A serializer for the model declaring a signing service.
    """

    pulp_href = base.IdentityField(view_name="signing-services-detail")
    name = serializers.CharField(help_text=_("A unique name used to recognize a script."))
    public_key = serializers.CharField(
        help_text=_("The value of a public key used for the repository verification.")
    )
    pubkey_fingerprint = serializers.CharField(help_text=_("The fingerprint of the public key."))
    script = serializers.CharField(
        help_text=_("An absolute path to a script which is going to be used for the signing.")
    )

    class Meta:
        model = models.SigningService
        fields = base.ModelSerializer.Meta.fields + (
            "name",
            "public_key",
            "pubkey_fingerprint",
            "script",
        )
