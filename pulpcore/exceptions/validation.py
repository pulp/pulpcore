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

    def __init__(self):
        super().__init__("PLP0003")

    def __str__(self):
        return _("A file failed validation due to checksum.")


class SizeValidationError(ValidationError):
    """
    Raised when a file fails to validate a size checksum.
    """

    def __init__(self):
        super().__init__("PLP0004")

    def __str__(self):
        return _("A file failed validation due to size.")


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
