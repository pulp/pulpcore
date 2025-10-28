from pulpcore.plugin import PulpPluginAppConfig


class PulpCertGuardPluginAppConfig(PulpPluginAppConfig):
    """App config for cert guard plugin."""

    name = "pulp_certguard.app"
    label = "certguard"
    version = "3.93.0.dev"
    python_package_name = "pulpcore"
    domain_compatible = True
