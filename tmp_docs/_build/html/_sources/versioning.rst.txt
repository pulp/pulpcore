.. _versioning:

Versioning
==========

Pulp uses a version scheme ``x.y.z``, which is based on `Semantic Versioning
<http://semver.org/>`_. Briefly, ``x.y.z`` releases may only contain bugfixes (no features),
``x.y`` releases may only contain backwards compatible changes (new features, bugfixes), and ``x``
releases may break backwards compatibility.

Plugin API
----------

The plugin API is provided by the pulpcore package and is not versioned independently. ``x.y.z``
releases of pulpcore should provide backwards compatible releases of the Plugin API but ``x.y``
releases might bring backwards incompatible changes of the plugin API.

We expect the plugin API to eventually be Semantically Versioned so that only ``x`` releases of
pulpcore will bring backwards incompatible changes to the plugin API. Until then, we recommend
plugins pin to ``x.y`` releases of pulpcore.
