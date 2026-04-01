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


class DuplicateContentInRepositoryError(ValidationError):
    """
    Raised when duplicate content is detected within a Repository (Version).
    """

    error_code = "PLP0022"

    def __init__(self, duplicate_count: int, correlation_id: str):
        self.dup_count = duplicate_count
        self.cid = correlation_id

    def __str__(self):
        return f"[{self.error_code}] " + _(
            "Found {n} duplicate contents in repository version"
            "(see the logs (cid={cid}) for details).".format(n=self.dup_count, cid=self.cid)
        )


class ContentOverwriteError(PulpException):
    """
    Raised when content would overwrite existing repository content and overwrite is disabled.
    """

    http_status_code = http.client.CONFLICT
    error_code = "PLP0023"

    def __init__(self, pulp_type, conflict_map):
        self.pulp_type = pulp_type
        self.conflict_map = conflict_map

    def __str__(self):
        pairs = ", ".join(
            f"{incoming}->{existing}" for incoming, existing in self.conflict_map.items()
        )
        return f"[{self.error_code}] " + _(
            "Content overwrite rejected: new content of type '{pulp_type}' would overwrite "
            "{n} existing content unit(s) in the repository based on repo_key_fields. "
            "Conflicting content (incoming->existing): [{pairs}]"
        ).format(pulp_type=self.pulp_type, n=len(self.conflict_map), pairs=pairs)
