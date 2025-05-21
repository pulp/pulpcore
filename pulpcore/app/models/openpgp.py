import re

from aiohttp.web_response import Response
from django.db import models
from django.utils import timezone
from pulpcore.app.models import AutoAddObjPermsMixin, Content, Distribution, Repository
from pulpcore.app.openpgp import wrap_armor
from pulpcore.app.util import get_domain_pk, gpg_verify


def _openpgp_packlen(length):
    if length < 192:
        return length.to_bytes(1, "big")
    if length < 8384:
        return (length + 48960).to_bytes(2, "big")
    return b"\xff" + length.to_bytes(4, "big")


class _OpenPGPContent(Content):
    # WARNING! This is an abstact class.
    # Never export it in the plugin api!
    raw_data = models.BinaryField()

    def packet(self):
        return (
            (0xC0 | self.PACKAGE_TYPE).to_bytes(1, "big")
            + _openpgp_packlen(len(self.raw_data))
            + self.raw_data
        )

    class Meta:
        abstract = True


class OpenPGPPublicKey(_OpenPGPContent):
    TYPE = "openpgp_publickey"
    repo_key_fields = ("fingerprint",)
    PACKAGE_TYPE = 6

    fingerprint = models.CharField(max_length=64)
    created = models.DateTimeField()
    _pulp_domain = models.ForeignKey("core.Domain", default=get_domain_pk, on_delete=models.PROTECT)

    def represent(self, repository_version=None):
        if repository_version:
            content_filter = {"pk__in": repository_version.content}
        else:
            content_filter = {}
        data = self.packet()
        for signature in self.openpgp_signatures.filter(**content_filter):
            data += signature.packet()
        for user_id in self.user_ids.filter(**content_filter):
            data += user_id.packet()
            for signature in user_id.openpgp_signatures.filter(**content_filter):
                data += signature.packet()
        for user_attribute in self.user_attributes.filter(**content_filter):
            data += user_attribute.packet()
            for signature in user_attribute.openpgp_signatures.filter(**content_filter):
                data += signature.packet()
        for public_subkey in self.public_subkeys.filter(**content_filter):
            data += public_subkey.packet()
            for signature in public_subkey.openpgp_signatures.filter(**content_filter):
                data += signature.packet()
        return wrap_armor(data)

    class Meta:
        default_related_name = "%(app_label)s_%(model_name)s"
        unique_together = (
            "_pulp_domain",
            "fingerprint",
        )


class OpenPGPPublicSubkey(_OpenPGPContent):
    TYPE = "openpgp_publicsubkey"
    repo_key_fields = ("public_key", "fingerprint")
    PACKAGE_TYPE = 14

    public_key = models.ForeignKey(
        OpenPGPPublicKey, related_name="public_subkeys", on_delete=models.PROTECT
    )
    fingerprint = models.CharField(max_length=64)
    created = models.DateTimeField()

    class Meta:
        default_related_name = "%(app_label)s_%(model_name)s"
        unique_together = (
            "public_key",
            "fingerprint",
        )


class OpenPGPUserID(_OpenPGPContent):
    TYPE = "openpgp_userid"
    repo_key_fields = ("public_key", "user_id")
    PACKAGE_TYPE = 13

    public_key = models.ForeignKey(
        OpenPGPPublicKey, related_name="user_ids", on_delete=models.PROTECT
    )
    user_id = models.CharField()

    class Meta:
        default_related_name = "%(app_label)s_%(model_name)s"
        unique_together = ("public_key", "user_id")


class OpenPGPUserAttribute(_OpenPGPContent):
    TYPE = "openpgp_userattribute"
    repo_key_fields = ("public_key", "sha256")
    PACKAGE_TYPE = 17

    sha256 = models.CharField(max_length=128)
    public_key = models.ForeignKey(
        OpenPGPPublicKey, related_name="user_attributes", on_delete=models.PROTECT
    )

    class Meta:
        default_related_name = "%(app_label)s_%(model_name)s"
        unique_together = ("public_key", "sha256")


class OpenPGPSignature(_OpenPGPContent):
    TYPE = "openpgp_signature"
    repo_key_fields = ("signed_content", "sha256")
    PACKAGE_TYPE = 2

    sha256 = models.CharField(max_length=128)
    signature_type = models.PositiveSmallIntegerField()
    created = models.DateTimeField()  # 2
    expiration_time = models.DurationField(null=True)  # 3
    key_expiration_time = models.DurationField(null=True)  # 9
    issuer = models.CharField(max_length=16, null=True)  # 16
    signers_user_id = models.CharField(null=True)  # 28
    signed_content = models.ForeignKey(
        Content, related_name="openpgp_signatures", on_delete=models.PROTECT
    )

    @property
    def expired(self):
        return self.expiration_time and timezone.now() > self.created + self.expiration_time

    @property
    def key_expired(self):
        if self.signature_type == 0x18:
            return (
                bool(self.key_expiration_time)
                and timezone.now() > self.signed_content.cast().created + self.key_expiration_time
            )
        # In case, we don't know or this is not applicable, return None, not False.
        return None

    class Meta:
        default_related_name = "%(app_label)s_%(model_name)s"
        unique_together = (
            "signed_content",
            "sha256",
        )


class OpenPGPKeyring(Repository, AutoAddObjPermsMixin):
    """A Repository to hold OpenPGP (rfc4880bis) public key material."""

    TYPE = "openpgp"
    CONTENT_TYPES = [
        OpenPGPPublicKey,
        OpenPGPUserID,
        OpenPGPUserAttribute,
        OpenPGPPublicSubkey,
        OpenPGPSignature,
    ]

    def gpg_verify(self, signature, detached_data=None):
        public_keys = "\n".join(
            [
                pubkey.represent(repository_version=self.latest_version())
                for pubkey in OpenPGPPublicKey.objects.filter(pk__in=self.latest_version().content)
            ]
        )
        return gpg_verify(public_keys, signature, detached_data)

    class Meta:
        default_related_name = "%(app_label)s_%(model_name)s"
        permissions = [
            ("modify_openpgpkeyring", "Can modify content of the keyring"),
            ("manage_roles_openpgpkeyring", "Can manage roles on keyrings"),
            ("repair_openpgpkeyring", "Can repair repository versions"),
        ]


class OpenPGPDistribution(Distribution, AutoAddObjPermsMixin):
    """A Distribution to allow downloading OpenPGP keys."""

    TYPE = "openpgp"
    SERVE_FROM_PUBLICATION = False
    PATH_REGEX = re.compile(r"(?P<key_id>[0-9a-fA-F]{16})\.pub")

    def content_handler(self, path):
        if result := self.PATH_REGEX.fullmatch(path):
            repository_version = self.repository_version or self.repository.latest_version()
            if repository_version is None:
                return None
            key_id = result.group("key_id")
            key = OpenPGPPublicKey.objects.filter(
                pk__in=repository_version.content, fingerprint__iendswith=key_id
            ).first()
            if key is None:
                return None
            return Response(
                text=key.represent(repository_version),
                content_type="application/pgp-keys",
                charset="us-ascii",
            )
        return None

    def content_handler_list_directory(self, rel_path):
        if rel_path == "":
            repository_version = self.repository_version or self.repository.latest_version()
            fingerprints = OpenPGPPublicKey.objects.filter(
                pk__in=repository_version.content
            ).values_list("fingerprint", flat=True)
            return {fingerprint[-16:] + ".pub" for fingerprint in fingerprints}
        return set()

    class Meta:
        default_related_name = "%(app_label)s_%(model_name)s"
        permissions = [
            ("manage_roles_openpgpdistribution", "Can manage roles on gem distributions"),
        ]
