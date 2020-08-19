Plugin API Reference
--------------------

The Plugin API is versioned separately from the Pulp Core and consists of everything importable
within the :mod:`pulpcore.plugin` namespace. When writing plugins, care should be taken to only
import Pulp Core components exposed in this namespace; importing from elsewhere within the Pulp
Core (e.g. importing directly from ``pulpcore.app``, ``pulpcore.exceptions``, etc.) is unsupported,
and not protected by the Pulp Plugin API's semantic versioning guarantees.

.. warning::

    Exactly what is versioned in the Plugin API, and how, still has yet to be determined.
    This documentation will be updated to clearly identify what guarantees come with the
    semantic versioning of the Plugin API in the future. As our initial plugins are under
    development prior to the release of Pulp 3.0, the Plugin API can be assumed to have
    semantic major version 0, indicating that it is unstable and still being developed.

.. toctree::
    models
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
