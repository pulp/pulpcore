from pulpcore.plugin import PulpPluginAppConfig


class PulpFilePluginAppConfig(PulpPluginAppConfig):
    """
    Entry point for pulp_file plugin.
    """

    name = "pulp_file.app"
    label = "file"
    version = "3.75.3.dev"
    python_package_name = "pulpcore"
    domain_compatible = True
