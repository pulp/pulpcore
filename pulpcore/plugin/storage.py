import os

from pulpcore.app.apps import get_plugin_config

from pulpcore.app.models.storage import get_tls_path


__all__ = ["get_plugin_storage_path", "get_tls_path"]


def get_plugin_storage_path(plugin_app_label):
    """
    Returns the path to the plugin's storage

    An interface for finding the path to a plugin's persistent storage location. It is
    designed to be used by plugins that need to store more than just
    :class:`~pulpcore.plugin.models.Artifact` models.

    Args:
        plugin_app_label (str): Django app label of the pulp plugin

    Returns:
        String containing the absolute path to the plugin's storage on the filesystem.

    Raises:
        :class:`~pulpcore.exceptions.plugin.MissingPlugin`: When plugin with the requested app
            label is not installed.
    """
    get_plugin_config(plugin_app_label)
    return os.path.join("/var/lib/pulp/shared", plugin_app_label, "")
