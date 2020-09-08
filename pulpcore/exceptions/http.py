import http.client
from gettext import gettext as _

from .base import PulpException


class MissingResource(PulpException):
    """
    Base class for missing resource exceptions.

    Exceptions that are raised due to requests for resources that do not exist should inherit
    from this base class.
    """

    http_status_code = http.client.NOT_FOUND

    def __init__(self, **resources):
        """
        :param resources: keyword arguments of resource_type=resource_id
        :type resources: dict
        """
        super().__init__("PLP0001")
        self.resources = resources

    def __str__(self):
        resources_str = ", ".join("%s=%s" % (k, v) for k, v in self.resources.items())
        msg = _("The following resources are missing: %s") % resources_str
        return msg.encode("utf-8")
