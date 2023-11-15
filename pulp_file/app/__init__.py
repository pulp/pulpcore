from pulpcore.plugin import PulpPluginAppConfig


class PulpFilePluginAppConfig(PulpPluginAppConfig):
    """
    Entry point for pulp_file plugin.
    """

    name = "pulp_file.app"
    label = "file"
    version = "3.42.0.dev"
    python_package_name = "pulp-file"  # TODO Add python_module_name
    domain_compatible = True
