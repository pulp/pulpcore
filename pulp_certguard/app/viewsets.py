from pulpcore.plugin.viewsets import ContentGuardFilter, ContentGuardViewSet

from .models import RHSMCertGuard, X509CertGuard
from .serializers import RHSMCertGuardSerializer, X509CertGuardSerializer


class RHSMCertGuardViewSet(ContentGuardViewSet):
    """RHSMCertGuard API Viewsets."""

    endpoint_name = "rhsm"
    queryset = RHSMCertGuard.objects.all()
    serializer_class = RHSMCertGuardSerializer
    filterset_class = ContentGuardFilter


class X509CertGuardViewSet(ContentGuardViewSet):
    """X509CertGuard API Viewsets."""

    endpoint_name = "x509"
    queryset = X509CertGuard.objects.all()
    serializer_class = X509CertGuardSerializer
    filterset_class = ContentGuardFilter
