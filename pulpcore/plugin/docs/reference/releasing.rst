Releasing Your Plugin
=====================

Packaging
---------

The Plugin API is available from PyPI as pulpcore-plugin. A plugin writer needs to specify the
minimum version of pulpcore-plugin their plugin is dependent on. A plugin writer does not need to
specify which version of pulpcore would work with their plugin since pulpcore-plugin will
resolve the pulpcore dependency.
