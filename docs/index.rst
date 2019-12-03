Pulp Documentation
==================

This documentation is for `pulpcore`, which is used with plugins to fetch, upload, and organize
arbitrary content types.

Anyone interested in writing a plugin should reference the :ref:`Plugin API`.


How to Navigate the pulpcore and plugin docs
--------------------------------------------

Plugin Documentation
^^^^^^^^^^^^^^^^^^^^

If you are a new user who is evaluating Pulp it is recommended that you skim the documentation for
the plugins that add the content types you are interested in. Links to these docs can be found in
our `list of plugins <https://pulpproject.org/pulp-3-plugins/>`_

Because the ecosystems of various content types (ie, rpm, docker) can be so diverse, `pulpcore`
stays out of the way for plugins that need to do something differently.

Each plugin can have different features, but as much as possible they follow common patterns to stay
consistent. The potential difference in workflows means that **each plugin is responsible for
documenting all workflows**. Some common plugin workflows the are:

* synchronize from an external repository
* add/remove content manually
* publish and host a repository version, enabling a client to download content
* deferred download (aka, on-demand sync)
* lifecycle management

Pulpcore Documentation
^^^^^^^^^^^^^^^^^^^^^^

`pulpcore` handles some parts of common content management workflows, including high performance
downloading, task queuing with scalable workers, and management of content within versioned
repositories. Information about :ref:`installation`, :ref:`deployment`, and :doc:`general concepts
and terminology<concepts>` are all covered by the ``pulpcore`` documentation.

 .. note::

    Some parts of the plugin workflows, like manual add/remove and lifecycle management are also
    documented in the pulpcore docs. These cover the common case, but not every plugin will use
    them.  This is why the plugin docs are the single source of truth for the workflows of each
    content type, and pulpcore docs are supplemental.

.. _community:

Community
---------

Pulp has an active commmunity that writes issues, fixes bugs, adds features, writes plugins,
and helps each other with support from the core developers. If you have questions or want to help
make Pulp better, please reach out!

* Usage discussions

  * pulp-list@redhat.com
  * #pulp channel on Freenode

* Development discussions

  * pulp-dev@redhat.com
  * #pulp-dev channel on Freenode

* Source code

  * `pulpcore <https://github.com/pulp/pulpcore/>`_
  * `pulp-smash (test suite) <https://github.com/PulpQE/pulp-smash>`_
  * `plugin table <https://pulpproject.org/pulp-3-plugins/>`_

    * Ansible #pulp-ansible channel on Freenode
    * Docker #pulp-docker channel on Freenode
    * Python #pulp-python channel on Freenode
    * RPM #pulp-rpm channel on Freenode


.. _versioning:

Versioning
----------

Pulp uses a version scheme ``x.y.z``, which is based on `Semantic Versioning
<http://semver.org/>`_. Briefly, ``x.y.z`` releases may only contain bugfixes (no features),
``x.y`` releases may only contain backwards compatible changes (new features, bugfixes), and ``x``
releases may break backwards compatibility.


Table of Contents
-----------------

.. toctree::
   :maxdepth: 2

   concepts
   from-pulp-2
   components
   installation/index
   settings
   workflows/index
   plugins/index
   rest_api
   client_bindings
   contributing/index
   bugs-features
   glossary
   changes
