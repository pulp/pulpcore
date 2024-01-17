from gettext import gettext as _

from OpenSSL import crypto as openssl

from pulpcore.plugin.serializers import ContentGuardSerializer

from rest_framework import serializers

from pulp_certguard.app.utils import get_rhsm
from .models import RHSMCertGuard, X509CertGuard


class BaseCertGuardSerializer(ContentGuardSerializer):
    """A Base Serializer class for all Cert Guard Serializers."""

    ca_certificate = serializers.CharField(
        help_text=_(
            "A Certificate Authority (CA) certificate (or a bundle thereof) "
            "used to verify client-certificate authenticity."
        ),
    )

    @staticmethod
    def validate_ca_certificate(ca_certificate):
        """Validates the given certificate as a PEM encoded X.509 certificate using openssl."""
        try:
            openssl.load_certificate(openssl.FILETYPE_PEM, buffer=ca_certificate)
        except (ValueError, openssl.Error):
            reason = _("Must be PEM encoded X.509 certificate.")
            raise serializers.ValidationError(reason)
        else:
            return ca_certificate

    class Meta:
        fields = ContentGuardSerializer.Meta.fields + ("ca_certificate",)


class RHSMCertGuardSerializer(BaseCertGuardSerializer):
    """RHSM Content Guard Serializer."""

    class Meta:
        model = RHSMCertGuard
        fields = BaseCertGuardSerializer.Meta.fields

    @staticmethod
    def validate_ca_certificate(ca_certificate):
        """Validates the given certificate."""
        get_rhsm()  # Validate that rhsm is installed
        return BaseCertGuardSerializer.validate_ca_certificate(ca_certificate)


class X509CertGuardSerializer(BaseCertGuardSerializer):
    """X.509 Content Guard Serializer."""

    class Meta:
        model = X509CertGuard
        fields = BaseCertGuardSerializer.Meta.fields
