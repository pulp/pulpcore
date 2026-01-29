from gettext import gettext as _
import http.client
from pulpcore.exceptions import PulpException


class ValidationError(PulpException):
    """
    A base class for all Validation Errors.
    """

    http_status_code = http.client.BAD_REQUEST
    error_code = "PLP0001"

    def __init__(self, msg):
        self.msg = msg

    def __str__(self):
        return f"[{self.error_code}] Validation Error: {self.msg}"


class DigestValidationError(ValidationError):
    """
    Raised when a file fails to validate a digest checksum.
    """

    error_code = "PLP0003"

    def __init__(self, actual, expected, *args, url=None, **kwargs):
        self.url = url
        self.actual = actual
        self.expected = expected

    def __str__(self):
        if self.url:
            msg = _(
                "A file located at the url {url} failed validation due to checksum. "
                "Expected '{expected}', Actual '{actual}'"
            )
            return f"[{self.error_code}] " + msg.format(
                url=self.url, expected=self.expected, actual=self.actual
            )
        else:
            msg = _(
                "A file failed validation due to checksum. Expected '{expected}', Actual '{actual}'"
            )
            return f"[{self.error_code}] " + msg.format(expected=self.expected, actual=self.actual)


class SizeValidationError(ValidationError):
    """
    Raised when a file fails to validate a size checksum.
    """

    error_code = "PLP0004"

    def __init__(self, actual, expected, *args, url=None, **kwargs):
        self.url = url
        self.actual = actual
        self.expected = expected

    def __str__(self):
        if self.url:
            msg = _(
                "A file located at the url {url} failed validation due to size. "
                "Expected '{expected}', Actual '{actual}'"
            )
            return f"[{self.error_code}] " + msg.format(
                url=self.url, expected=self.expected, actual=self.actual
            )
        else:
            msg = _(
                "A file failed validation due to size. Expected '{expected}', Actual '{actual}'"
            )
            return f"[{self.error_code}] " + msg.format(expected=self.expected, actual=self.actual)


class MissingDigestValidationError(ValidationError):
    """
    Raised when attempting to save() an Artifact with an incomplete set of checksums.
    """

    error_code = "PLP0019"

    def __init__(self, message=None):
        self.message = message or _("Artifact is missing required checksums.")

    def __str__(self):
        return f"[{self.error_code}] {self.message}"


class UnsupportedDigestValidationError(ValidationError):
    """
    Raised when an attempt is made to use a checksum-type that is not enabled/available.
    """

    error_code = "PLP0020"

    def __init__(self, digest_name=None):
        self.digest_name = digest_name

    def __str__(self):
        if self.digest_name:
            return f"[{self.error_code}] " + _(
                "Checksum type '{digest}' is not supported or enabled."
            ).format(digest=self.digest_name)
        return f"[{self.error_code}] " + _("Unsupported checksum type.")


class InvalidSignatureError(ValidationError):
    """
    Raised when a signature could not be verified by the GnuPG utility.
    """

    error_code = "PLP0021"

    def __init__(self, message=None, verified=None):
        self.message = message or _("Signature verification failed.")
        self.verified = verified

    def __str__(self):
        return f"[{self.error_code}] {self.message}"
