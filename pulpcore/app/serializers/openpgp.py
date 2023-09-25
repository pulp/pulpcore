from gettext import gettext as _

from pulpcore.app import models
from pulpcore.app.openpgp import read_public_key
from pulpcore.app.serializers import (
    DetailRelatedField,
    DistributionSerializer,
    NoArtifactContentSerializer,
    RepositorySerializer,
    RepositoryVersionRelatedField,
)
from pulpcore.app.util import get_domain_pk
from pulpcore.plugin.serializers import NoArtifactContentUploadSerializer
from rest_framework import serializers


class NestedOpenPGPSignatureSerializer(NoArtifactContentSerializer):
    expired = serializers.BooleanField()

    class Meta:
        model = models.OpenPGPSignature
        fields = (
            "issuer",
            "created",
            "expiration_time",
            "signers_user_id",
            "key_expiration_time",
            "expired",
            "key_expired",
        )


class OpenPGPSignatureSerializer(NestedOpenPGPSignatureSerializer):
    signed_content = DetailRelatedField(
        view_name_pattern=r"content(-.*/.*)-detail",
        read_only=True,
    )

    def retrieve(self, validated_data):
        return models.OpenPGPSignature.objects.filter(
            signed_content=validated_data["signed_content"], sha256=validated_data["sha256"]
        ).first()

    def create(self, validated_data):
        signature = super().create(validated_data)
        self.context["added_content_pks"].add(signature.pk)
        return signature

    class Meta:
        model = models.OpenPGPSignature
        fields = (
            NoArtifactContentSerializer.Meta.fields
            + NestedOpenPGPSignatureSerializer.Meta.fields
            + ("signed_content",)
        )


class NestedOpenPGPUserIDSerializer(NoArtifactContentSerializer):
    signatures = NestedOpenPGPSignatureSerializer(
        many=True, read_only=True, source="openpgp_signatures"
    )

    class Meta:
        model = models.OpenPGPUserID
        fields = ("user_id", "signatures")


class OpenPGPUserIDSerializer(NestedOpenPGPUserIDSerializer):
    public_key = DetailRelatedField(
        view_name=r"content-core/openpgp_publickey-detail",
        read_only=True,
    )

    def retrieve(self, validated_data):
        return models.OpenPGPUserID.objects.filter(
            public_key=validated_data["public_key"], user_id=validated_data["user_id"]
        ).first()

    def create(self, validated_data):
        signatures_data = validated_data.pop("signatures")
        user_id = super().create(validated_data)
        self.context["added_content_pks"].add(user_id.pk)
        for data in signatures_data:
            OpenPGPSignatureSerializer(context=self.context).create(
                {"signed_content": user_id, **data}
            )
        return user_id

    class Meta:
        model = models.OpenPGPUserID
        fields = (
            NoArtifactContentSerializer.Meta.fields
            + NestedOpenPGPUserIDSerializer.Meta.fields
            + ("public_key",)
        )


class NestedOpenPGPUserAttributeSerializer(NoArtifactContentSerializer):
    signatures = NestedOpenPGPSignatureSerializer(
        many=True, read_only=True, source="openpgp_signatures"
    )

    class Meta:
        model = models.OpenPGPUserAttribute
        fields = ("sha256", "signatures")


class OpenPGPUserAttributeSerializer(NestedOpenPGPUserAttributeSerializer):
    public_key = DetailRelatedField(
        view_name=r"content-core/openpgp_publickey-detail",
        read_only=True,
    )

    def retrieve(self, validated_data):
        return models.OpenPGPUserAttribute.objects.filter(
            public_key=validated_data["public_key"], sha256=validated_data["sha256"]
        ).first()

    def create(self, validated_data):
        signatures_data = validated_data.pop("signatures")
        user_attribute = super().create(validated_data)
        self.context["added_content_pks"].add(user_attribute.pk)
        for data in signatures_data:
            OpenPGPSignatureSerializer(context=self.context).create(
                {"signed_content": user_attribute, **data}
            )
        return user_attribute

    class Meta:
        model = models.OpenPGPUserAttribute
        fields = (
            NoArtifactContentSerializer.Meta.fields
            + NestedOpenPGPUserAttributeSerializer.Meta.fields
            + ("public_key", "sha256")
        )


class NestedOpenPGPPublicSubkeySerializer(NoArtifactContentSerializer):
    signatures = NestedOpenPGPSignatureSerializer(
        many=True, read_only=True, source="openpgp_signatures"
    )

    class Meta:
        model = models.OpenPGPPublicSubkey
        fields = (
            "fingerprint",
            "created",
            "signatures",
        )


class OpenPGPPublicSubkeySerializer(NestedOpenPGPPublicSubkeySerializer):
    public_key = DetailRelatedField(
        view_name=r"content-core/openpgp_publickey-detail",
        read_only=True,
    )

    def retrieve(self, validated_data):
        return models.OpenPGPPublicSubkey.objects.filter(
            public_key=validated_data["public_key"], fingerprint=validated_data["fingerprint"]
        ).first()

    def create(self, validated_data):
        signatures_data = validated_data.pop("signatures")
        public_subkey = super().create(validated_data)
        self.context["added_content_pks"].add(public_subkey.pk)
        for data in signatures_data:
            OpenPGPSignatureSerializer(context=self.context).create(
                {"signed_content": public_subkey, **data}
            )
        return public_subkey

    class Meta:
        model = models.OpenPGPPublicSubkey
        fields = (
            NoArtifactContentSerializer.Meta.fields
            + NestedOpenPGPPublicSubkeySerializer.Meta.fields
            + ("public_key",)
        )


class OpenPGPPublicKeySerializer(NoArtifactContentUploadSerializer):
    fingerprint = serializers.CharField(max_length=64, read_only=True)
    created = serializers.DateTimeField(read_only=True)
    user_ids = NestedOpenPGPUserIDSerializer(many=True, read_only=True)
    user_attributes = NestedOpenPGPUserAttributeSerializer(many=True, read_only=True)
    public_subkeys = NestedOpenPGPPublicSubkeySerializer(many=True, read_only=True)

    def deferred_validate(self, data):
        data = super().deferred_validate(data)
        file = data.pop("file")
        try:
            data.update(read_public_key(file.read()))
        except (ValueError, NotImplementedError) as e:
            raise serializers.ValidationError(str(e))
        return data

    def retrieve(self, validated_data):
        return models.OpenPGPPublicKey.objects.filter(
            pulp_domain=get_domain_pk(), fingerprint=validated_data["fingerprint"]
        ).first()

    def create(self, validated_data):
        # We need to handle that ourselves to not create a bunch of versions here.
        repository = validated_data.pop("repository", None)

        signatures_data = validated_data.pop("signatures")
        user_ids_data = validated_data.pop("user_ids")
        user_attributes_data = validated_data.pop("user_attributes")
        public_subkeys_data = validated_data.pop("public_subkeys")

        public_key = super().create(validated_data)
        self.context["added_content_pks"] = {public_key.pk}
        for data in signatures_data:
            OpenPGPSignatureSerializer(context=self.context).create(
                {"signed_content": public_key, **data}
            )
        for data in user_ids_data:
            OpenPGPUserIDSerializer(context=self.context).create({"public_key": public_key, **data})
        for data in user_attributes_data:
            OpenPGPUserAttributeSerializer(context=self.context).create(
                {"public_key": public_key, **data}
            )
        for data in public_subkeys_data:
            OpenPGPPublicSubkeySerializer(context=self.context).create(
                {"public_key": public_key, **data}
            )

        if repository:
            with repository.new_version() as new_version:
                new_version.add_content(
                    models.Content.objects.filter(pk__in=self.context["added_content_pks"])
                )

        return public_key

    class Meta:
        model = models.OpenPGPPublicKey
        fields = NoArtifactContentUploadSerializer.Meta.fields + (
            "fingerprint",
            "created",
            "user_ids",
            "user_attributes",
            "public_subkeys",
        )


class OpenPGPKeyringSerializer(RepositorySerializer):
    class Meta:
        fields = RepositorySerializer.Meta.fields
        model = models.OpenPGPKeyring


class OpenPGPDistributionSerializer(DistributionSerializer):
    repository_version = RepositoryVersionRelatedField(
        required=False, help_text=_("RepositoryVersion to be served"), allow_null=True
    )

    class Meta:
        fields = DistributionSerializer.Meta.fields + ("repository_version",)
        model = models.OpenPGPDistribution
