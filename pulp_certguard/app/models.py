from logging import getLogger
from gettext import gettext as _
import re
from urllib.parse import unquote

from django.conf import settings
from django.db import models

from OpenSSL import crypto as openssl

from pulpcore.plugin.models import ContentGuard

from pulp_certguard.app.utils import get_rhsm

try:
    from rhsm import certificate
except ImportError:
    pass


logger = getLogger(__name__)

cert_unquoted_body_regex = re.compile("^-----BEGIN CERTIFICATE-----(.*)-----END CERTIFICATE-----")


class BaseCertGuard(ContentGuard):
    """A Base class all CertGuard implementations should derive from."""

    ca_certificate = models.TextField()

    @staticmethod
    def _reassemble_client_cert(unquoted_client_cert):
        match_result = cert_unquoted_body_regex.match(unquoted_client_cert)
        if match_result:
            cert_body = match_result.groups()[0]
            logger.debug("Reassembled client certificate")
            reassembled_client_cert = (
                "-----BEGIN CERTIFICATE-----"
                + cert_body.replace(" ", "\n")
                + "-----END CERTIFICATE-----"
                + "\n"
            )
            return reassembled_client_cert
        else:
            logger.debug("Did *not* have to reassemble client cert")
            return unquoted_client_cert

    @classmethod
    def _get_client_cert_header(cls, request):
        try:
            client_cert_data = request.headers["X-CLIENT-CERT"]
            logger.debug(f"client_cert_data received: {client_cert_data}")
        except KeyError:
            msg = _("A client certificate was not received via the `X-CLIENT-CERT` header.")
            logger.warning(msg)
            raise PermissionError(msg)
        unquoted_client_cert = unquote(client_cert_data)
        return cls._reassemble_client_cert(unquoted_client_cert)

    def _ensure_client_cert_is_trusted(self, unquoted_certificate):
        trust_store = self._build_trust_store()

        try:
            openssl_client_cert = openssl.load_certificate(
                openssl.FILETYPE_PEM, buffer=unquoted_certificate
            )
        except openssl.Error as exc:
            msg = str(exc)
            logger.warning(msg)
            raise PermissionError(msg)

        try:
            context = openssl.X509StoreContext(
                certificate=openssl_client_cert,
                store=trust_store,
            )
            context.verify_certificate()
        except openssl.X509StoreContextError as exc:
            msg = str(exc)
            if exc.args[0][0] == 20:  # The error code for client cert not signed by the CA
                msg = _("Client certificate is not signed by the stored 'ca_certificate'.")
            elif exc.args[0][0] == 10:  # The error code for an expired certificate
                msg = _("Client certificate is expired.")
            logger.warning(msg)
            raise PermissionError(msg)
        except openssl.Error as exc:
            msg = str(exc)
            logger.warning(msg)
            raise PermissionError(msg)

    def _build_trust_store(self):
        trust_store = openssl.X509Store()

        # self.ca_certificate can be a **bundle** of certificates, which must be added to
        # X509Store one at a time.
        # We break ca_certificate up along BEGIN-CERTIFICATE/END-CERTIFICATE lines.
        # Certs can come with non-cert content (e.g. embedded-human-readable format inline);
        # hence, the following reg-ex throws out lines that don't exist between BEGIN/END pairs,
        # and builds certs out of the retained lines.
        rx = re.compile(
            r"(-----BEGIN CERTIFICATE-----.*?-----END CERTIFICATE-----)", re.MULTILINE | re.DOTALL
        )
        ca_certs = rx.findall(str(self.ca_certificate))

        # Now load each resulting cert, and set up in the trust_store
        for crt in ca_certs:
            try:
                openssl_ca_cert = openssl.load_certificate(
                    openssl.FILETYPE_PEM, buffer=crt.encode()
                )
            except openssl.Error as exc:
                logger.warning(str(exc))
                raise PermissionError(str(exc))
            trust_store.add_cert(openssl_ca_cert)

        # If we get this far - return the now-loaded store!
        return trust_store

    class Meta:
        abstract = True


class RHSMCertGuard(BaseCertGuard):
    """
    A content-guard validating on a RHSM Certificate validated by `python-rhsm`.

    A Certificate Authority certificate to trust is required with each RHSMCertGuard created. With
    each request, the client certificate is first checked if it is signed by this CA cert. If not,
    it's untrusted and denied regardless of its paths.

    After determining the client certificate is trusted, the requested path is checked against the
    named paths in the certificate. A request is permitted if the current request path is a prefix
    of a path declared in the trusted RHSM Client Certificate.

    Fields:
        rhsm_certificate (models.TextField): The RHSM Certificate used to validate the client
            certificate at request time.
    """

    TYPE = "rhsm"

    def __init__(self, *args, **kwargs):
        """Initialize a RHSMCertGuard and ensure this system has python-rhsm on it."""
        get_rhsm()  # Validate that rhsm is installed
        super().__init__(*args, **kwargs)

    class Meta:
        default_related_name = "%(app_label)s_%(model_name)s"

    def permit(self, request):
        """
        Validate the client cert is trusted and asserts a path that is prefix of the requested path.

        Args:
            request: The request from the user.

        Raises:
            PermissionError: If the request path is not a subpath of a path named in the
                certificate, or if the client certificate is not trusted from the CA certificated
                stored as `ca_certificate`.
        """
        get_rhsm()
        unquoted_certificate = self._get_client_cert_header(request)
        self._ensure_client_cert_is_trusted(unquoted_certificate)
        rhsm_cert = self._create_rhsm_cert_from_pem(unquoted_certificate)
        content_path_prefix_without_trail_slash = settings.CONTENT_PATH_PREFIX.rstrip("/")
        len_prefix_to_remove = len(content_path_prefix_without_trail_slash)
        path_without_content_path_prefix = request.path[len_prefix_to_remove:]
        self._check_paths(rhsm_cert, path_without_content_path_prefix)

    @staticmethod
    def _create_rhsm_cert_from_pem(unquoted_certificate):
        try:
            rhsm_cert = certificate.create_from_pem(unquoted_certificate)
        except certificate.CertificateException:
            msg = _("An error occurred while loading the client certificate data into python-rhsm.")
            logger.warning(msg)
            raise PermissionError(msg)
        return rhsm_cert

    @staticmethod
    def _check_paths(rhsm_cert, path):
        logger.debug(f"Checking that path {path} is allowed in client cert")
        if rhsm_cert.check_path(path) is False:
            logger.warning(f"Path {path} is *not* allowed in client cert")
            msg = _("Requested path is not a subpath of a path in the client certificate.")
            raise PermissionError(msg)


class X509CertGuard(BaseCertGuard):
    """
    A content-guard that authenticates the request based on a client provided X.509 Certificate.

    Fields:
        ca_certificate (models.FileField): The CA certificate used to
            validate the client certificate.
    """

    TYPE = "x509"

    def permit(self, request):
        """
        Validate the client cert is trusted.

        Args:
            request: The request from the user.

        Raises:
            PermissionError: If the client certificate is not trusted from the CA certificated
                stored as `ca_certificate`.
        """
        unquoted_certificate = self._get_client_cert_header(request)
        self._ensure_client_cert_is_trusted(unquoted_certificate)

    class Meta:
        default_related_name = "%(app_label)s_%(model_name)s"
