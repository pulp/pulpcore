from gettext import gettext as _

from pulpcore.exceptions import PulpException


class ValidationError(PulpException):
    """
    A base class for all Validation Errors.
    """

    pass


class DigestValidationError(ValidationError):
    """
    Raised when a file fails to validate a digest checksum.
    """

    def __init__(self, actual, expected, *args, url=None, **kwargs):
        super().__init__("PLP0003")
        self.url = url
        self.actual = actual
        self.expected = expected

    def __str__(self):
        if self.url:
            msg = _(
                "A file located at the url {url} failed validation due to checksum. "
                "Expected '{expected}', Actual '{actual}'"
            )
            return msg.format(url=self.url, expected=self.expected, actual=self.actual)
        else:
            msg = _(
                "A file failed validation due to checksum. Expected '{expected}', Actual '{actual}'"
            )
            return msg.format(expected=self.expected, actual=self.actual)


class SizeValidationError(ValidationError):
    """
    Raised when a file fails to validate a size checksum.
    """

    def __init__(self, actual, expected, *args, url=None, **kwargs):
        super().__init__("PLP0004")
        self.url = url
        self.actual = actual
        self.expected = expected

    def __str__(self):
        if self.url:
            msg = _(
                "A file located at the url {url} failed validation due to size. "
                "Expected '{expected}', Actual '{actual}'"
            )
            return msg.format(url=self.url, expected=self.expected, actual=self.actual)
        else:
            msg = _(
                "A file failed validation due to size. Expected '{expected}', Actual '{actual}'"
            )
            return msg.format(expected=self.expected, actual=self.actual)


class MissingDigestValidationError(Exception):
    """
    Raised when attempting to save() an Artifact with an incomplete set of checksums.
    """

    pass


class UnsupportedDigestValidationError(Exception):
    """
    Raised when an attempt is made to use a checksum-type that is not enabled/available.
    """

    pass


class InvalidSignatureError(RuntimeError):
    """
    Raised when a signature could not be verified by the GnuPG utility.
    """

    def __init__(self, *args, **kwargs):
        self.verified = kwargs.pop("verified", None)
        super().__init__(*args, **kwargs)
