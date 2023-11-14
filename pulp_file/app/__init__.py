from pulpcore.plugin import PulpPluginAppConfig


class PulpFilePluginAppConfig(PulpPluginAppConfig):
    """
    Entry point for pulp_file plugin.
    """

    name = "pulp_file.app"
    label = "file"
    version = "3.41.0"
    python_package_name = "pulp_file"  # TODO Add python_module_name
    domain_compatible = True
