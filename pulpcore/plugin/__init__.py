# plugins declare that they are a pulp plugin by subclassing PulpPluginAppConfig
from pulpcore.app.apps import PulpPluginAppConfig  # noqa

# allow plugins to access the pulpcore version
from pulpcore import __version__ as pulpcore_version  # noqa
