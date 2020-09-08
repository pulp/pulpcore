from gettext import gettext as _

from .base import PulpException


class MissingPlugin(PulpException):
    """
    Missing plugin exception.

    Exception that is raised when a requested plugin is not installed.
    """

    def __init__(self, plugin_app_label):
        """
        :param resources: keyword arguments of resource_type=resource_id
        :type resources: dict
        """
        super().__init__("PLP0002")
        self.plugin_app_label = plugin_app_label

    def __str__(self):
        msg = _("Plugin with Django app label %s is not installed.") % self.plugin_app_label
        return msg
