import http.client
from gettext import gettext as _
from pulpcore.app.loggers import deprecation_logger


class PulpException(Exception):
    """
    Base exception class for Pulp.
    """

    http_status_code = http.client.INTERNAL_SERVER_ERROR
    error_code = None

    def __init__(self, error_code=None):
        if error_code:
            deprecation_logger.warning(
                "Constructing a PulpException with argument `error_code` is deprecated and will "
                "be removed in a future release. Instead please create a new error Subclass with "
                "predefined `error_code` attribute"
            )
            self.error_code = error_code
        if not isinstance(self.error_code, str):
            raise NotImplementedError("ABC error. Subclass must define a unique error code.")

    def __str__(self):
        """
        Returns the string representation of the exception.

        Each concrete class that inherits from [pulpcore.server.exception.PulpException][] is
        expected to implement it's own __str__() method. The return value is used by Pulp when
        recording the exception in the database.
        """
        raise NotImplementedError("Subclasses of PulpException must implement a __str__() method")


def exception_to_dict(exc, traceback=None):
    """
    Return a dictionary representation of an Exception.

    :param exc: Exception that is being serialized
    :type exc: Exception
    :param traceback: String representation of a traceback generated when the exception occurred.
    :type traceback: str

    :return: dictionary representing the Exception
    :rtype: dict
    """
    dic = {"description": str(exc), "traceback": traceback}
    if isinstance(exc, PulpException):
        dic["error_code"] = exc.error_code
    return dic


class InternalErrorException(PulpException):
    """
    Exception to signal that an unexpected internal error occurred.
    """

    error_code = "PLP0000"

    def __str__(self):
        return f"[{self.error_code}] " + _("An internal error occurred.")


class ResourceImmutableError(PulpException):
    """
    Exceptions that are raised due to trying to update an immutable resource
    """

    error_code = "PLP0006"

    def __init__(self, model):
        """
        Args:
            model (pulpcore.app.models.Model): that the user is trying to update
        """
        self.model = model

    def __str__(self):
        msg = _("Cannot update immutable resource {model_pk} of type {model_type}").format(
            resource=str(self.model.pk), type=type(self.model).__name__
        )
        return f"[{self.error_code}] {msg}"


class TimeoutException(PulpException):
    """
    Exception to signal timeout error.
    """

    error_code = "PLP0005"

    def __init__(self, url):
        """
        :param url: the url the download for timed out
        :type url: str
        """
        self.url = url

    def __str__(self):
        return f"[{self.error_code}] " + _(
            "Request timed out for {}. Increasing the total_timeout value on the remote might help."
        ).format(self.url)


class DomainProtectedError(PulpException):
    """
    Exception to signal that a domain the user is trying to delete still contains
    repositories with content.
    """

    error_code = "PLP0007"

    def __str__(self):
        return f"[{self.error_code}] " + _(
            "You cannot delete a domain that still contains repositories with content."
        )


class DnsDomainNameException(PulpException):
    """
    Exception to signal that dns could not resolve the domain name for specified url.
    """

    error_code = "PLP0008"

    def __init__(self, url):
        """
        :param url: the url that dns could not resolve
        :type url: str
        """
        self.url = url

    def __str__(self):
        return f"[{self.error_code}] " + _("URL lookup failed.")


class UrlSchemeNotSupportedError(PulpException):
    """
    Exception raised when a URL scheme (e.g. 'ftp://') is provided that
    Pulp does not have a registered handler for.
    """

    error_code = "PLP0009"

    def __init__(self, url):
        """
        :param url: The full URL that failed validation.
        :type url: str
        """
        self.url = url

    def __str__(self):
        return f"[{self.error_code}] " + _("URL: {u} not supported.").format(u=self.url)


class ProxyAuthenticationError(PulpException):
    """
    Exception to signal that the proxy server requires authentication
    but it was not provided or is invalid
    """

    error_code = "PLP0010"

    def __init__(self, proxy_url):
        """
        :param proxy_url: The URL of the proxy server.
        :type proxy_url: str
        """
        self.proxy_url = proxy_url

    def __str__(self):
        return f"[{self.error_code}] " + _(
            "Proxy authentication failed for {proxy_url}. Please check your proxy credentials."
        ).format(proxy_url=self.proxy_url)


class RepositoryVersionDeleteError(PulpException):
    """
    Raised when attempting to delete a repository version that cannot be deleted
    """

    http_status_code = http.client.BAD_REQUEST
    error_code = "PLP0011"

    def __init__(self, message=None):
        """
        :param message: Description of the repository version delete error
        :type message: str
        """
        self.message = message or _(
            "Cannot delete repository version. Repositories must have at least one repository "
            "version."
        )

    def __str__(self):
        return f"[{self.error_code}] " + self.message


class PublishError(PulpException):
    """
    Raised when a publish operation fails.
    """

    error_code = "PLP0012"

    def __init__(self, message=None):
        """
        :param message: Description of the publish error
        :type message: str
        """
        self.message = message

    def __str__(self):
        return f"[{self.error_code}] " + _("Publish failed: {message}").format(message=self.message)


class SyncError(PulpException):
    """
    Raised when a sync operation fails.
    """

    error_code = "PLP0013"

    def __init__(self, message):
        """
        :param message: Description of the sync error
        :type message: str
        """
        self.message = message

    def __str__(self):
        return f"[{self.error_code}] " + _("Sync failed: {message}").format(message=self.message)


class ExternalServiceError(PulpException):
    """
    Raised when an external API or service fails.
    """

    http_status_code = http.client.BAD_GATEWAY
    error_code = "PLP0014"

    def __init__(self, service_name, details=None):
        """
        :param service_name: Name of the external service
        :type service_name: str
        :param details: Additional details about the failure
        :type details: str or None
        """
        self.service_name = service_name
        self.details = details

    def __str__(self):
        msg = _("External service '{service}' failed").format(service=self.service_name)
        if self.details:
            msg += f": {self.details}"
        return f"[{self.error_code}] {msg}"


class ExportError(PulpException):
    """
    Raised when export operation fails due to configuration or preconditions.
    """

    http_status_code = http.client.BAD_REQUEST
    error_code = "PLP0015"

    def __init__(self, message):
        """
        :param message: Description of the export error
        :type message: str
        """
        self.message = message

    def __str__(self):
        return f"[{self.error_code}] " + _("Export failed: {message}").format(message=self.message)


class ImportError(PulpException):
    """
    Raised when an import operation fails due to configuration or preconditions.
    """

    http_status_code = http.client.BAD_REQUEST
    error_code = "PLP0016"

    def __init__(self, message):
        """
        :param message: Description of the import error
        :type message: str
        """
        self.message = message

    def __str__(self):
        return f"[{self.error_code}] " + _("Import failed: {message}").format(message=self.message)


class SystemStateError(PulpException):
    """
    Raised when system is in an unexpected state.
    """

    error_code = "PLP0017"

    def __init__(self, message):
        """
        :param message: Description of the system state error
        :type message: str
        """
        self.message = message

    def __str__(self):
        return f"[{self.error_code}] " + _("System state error: {message}").format(
            message=self.message
        )


class ReplicateError(PulpException):
    """
    Raised when a replicate operation fails.
    """

    error_code = "PLP0018"

    def __str__(self):
        return f"[{self.error_code}] " + _("Replication failed")
