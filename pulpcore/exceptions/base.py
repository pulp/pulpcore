import http.client
from gettext import gettext as _


class PulpException(Exception):
    """
    Base exception class for Pulp.
    """

    http_status_code = http.client.INTERNAL_SERVER_ERROR

    def __init__(self, error_code):
        """
        :param error_code: unique error code
        :type error_code: str
        """
        if not isinstance(error_code, str):
            raise TypeError(_("Error code must be an instance of str."))
        self.error_code = error_code

    def __str__(self):
        """
        Returns the string representation of the exception.

        Each concrete class that inherits from [pulpcore.server.exception.PulpException][] is
        expected to implement it's own __str__() method. The return value is used by Pulp when
        recording the exception in the database.
        """
        raise NotImplementedError("Subclasses of PulpException must implement a __str__() method")


def exception_to_dict(exc):
    """
    Return a dictionary representation of an Exception.

    :param exc: Exception that is being serialized
    :type exc: Exception

    :return: dictionary representing the Exception
    :rtype: dict
    """
    return {"description": str(exc)}


class InternalErrorException(PulpException):
    """
    Exception to signal that an unexpected internal error occurred.
    """

    def __init__(self):
        super().__init__("PLP0000")

    def __str__(self):
        return f"[{self.error_code}] " + _("An internal error occurred.")


class ResourceImmutableError(PulpException):
    """
    Exceptions that are raised due to trying to update an immutable resource
    """

    def __init__(self, model):
        """
        Args:
            model (pulpcore.app.models.Model): that the user is trying to update
        """
        super().__init__("PLP0006")
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

    def __init__(self, url):
        """
        :param url: the url the download for timed out
        :type url: str
        """
        super().__init__("PLP0005")
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

    def __init__(self):
        super().__init__("PLP0007")

    def __str__(self):
        return f"[{self.error_code}] " + _(
            "You cannot delete a domain that still contains repositories with content."
        )


class DnsDomainNameException(PulpException):
    """
    Exception to signal that dns could not resolve the domain name for specified url.
    """

    def __init__(self, url):
        """
        :param url: the url that dns could not resolve
        :type url: str
        """
        super().__init__("PLP0008")
        self.url = url

    def __str__(self):
        return f"[{self.error_code}] " + _("URL lookup failed.")


class UrlSchemeNotSupportedError(PulpException):
    """
    Exception raised when a URL scheme (e.g. 'ftp://') is provided that
    Pulp does not have a registered handler for.
    """

    def __init__(self, url):
        """
        :param url: The full URL that failed validation.
        :type url: str
        """
        super().__init__("PLP0009")
        self.url = url

    def __str__(self):
        return f"[{self.error_code}] " + _("URL: {u} not supported.").format(u=self.url)


class ProxyAuthenticationError(PulpException):
    """
    Exception to signal that the proxy server requires authentication
    but it was not provided or is invalid
    """

    def __init__(self, proxy_url):
        """
        :param proxy_url: The URL of the proxy server.
        :type proxy_url: str
        """
        super().__init__("PLP0010")
        self.proxy_url = proxy_url

    def __str__(self):
        return f"[{self.error_code}] " + _(
            "Proxy authentication failed for {proxy_url}. Please check your proxy credentials."
        ).format(proxy_url=self.proxy_url)


class RepositoryVersionDeleteError(PulpException):
    """
    Raised when attempting to delete a repository version that cannot be deleted
    """

    def __init__(self):
        super().__init__("PLP0011")

    def __str__(self):
        return f"[{self.error_code}] " + _(
            "Cannot delete repository version. Repositories must have at least one "
            "repository version."
        )
