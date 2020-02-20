Releasing Your Plugin
=====================

Depending on pulpcore
---------------------

A plugin writer should specify specify the minimum and maximum version of pulpcore their plugin
requires. The Plugin API is not yet stable so plugins should pin on a specific 3.y version of
pulpcore. For example, if your plugin requires 3.0 and is also compatible with pulpcore 3.1, you
want to restrict it to::

    pulpcore>=3.0,<3.2

This ensures that if pulpcore==3.2 releases and contains backwards incompatible changes, your users
won't upgrade into an environment with an incompatible pulpcore.
