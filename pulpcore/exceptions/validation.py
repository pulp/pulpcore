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

    def __init__(self, *args):
        super().__init__("PLP0003")
        if args:
            self.url = args[0]

    def __str__(self):
        if hasattr(self, "url"):
            return _("A file located at the url {} failed validation due to checksum.").format(
                self.url
            )
        return _("A file failed validation due to checksum.")


class SizeValidationError(ValidationError):
    """
    Raised when a file fails to validate a size checksum.
    """

    def __init__(self, *args):
        super().__init__("PLP0004")
        if args:
            self.url = args[0]

    def __str__(self):
        if hasattr(self, "url"):
            return _("A file located at the url {} failed validation due to size.").format(self.url)
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
