Pulp Documentation
==================

The documentation presented here is generalized to all content types. Information for managing each
content type is provided by the corresponding plugin, which can be found in our
`list of plugins <https://pulpproject.org/pulp-3-plugins/>`_.

Developers interested in writing plugins should reference the `Pulp Plugin API
<../../pulpcore-plugin/nightly/>`_ documentation.


Self-Guided Tour for New Users
------------------------------

A good place for new users to start is the :doc:`concepts`, which gives a high level
introduction to Pulp concepts, terminology, and components. After :doc:`installing
pulp<installation/index>`, the simplest way to get concrete experience is to install one of the
`plugins <https://pulpproject.org/pulp-3-plugins/>`_ and use its quickstart guide. Next it is
recommended that users read through our :doc:`workflows/index` to find best practices for common
use cases.


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
   plugins/index
   workflows/index
   release-notes/index
   integration-guide/index
   contributing/index
   troubleshooting
   bugs-features
   glossary
