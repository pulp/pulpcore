Plugin API Reference
--------------------

The Plugin API is versioned in sync with ``pulpcore`` and consists of everything importable within the
:mod:`pulpcore.plugin` namespace. It is governed by our `deprecation policy <_deprecation_policy>`_.
When writing plugins, care should be taken to only import ``pulpcore`` components exposed in this
namespace; importing from elsewhere within the ``pulpcore`` module (e.g. importing directly from
``pulpcore.app``, ``pulpcore.exceptions``, etc.) is unsupported, and not protected by the
aforementioned Pulp Plugin API deprecation policy.


.. toctree::
    models
    exceptions
    serializers
    storage
    viewsets
    tasking
    download
    stages
    profiling
    content-app


.. automodule:: pulpcore.plugin
    :imported-members:
    :members:
