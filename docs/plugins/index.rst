Plugins
=======

Plugins add support for a type of content to Pulp. For example, the
`file_plugin <https://github.com/pulp/pulp_file>`_ adds support for Pulp to manage files.

Each plugin has its own documentation that contains setup, workflow, and conceptual information:

* `Pulp RPM plugin <https://docs.pulpproject.org/pulp_rpm/>`_.
* `Pulp File plugin <https://docs.pulpproject.org/pulp_file/>`_.
* `Pulp Container plugin <https://docs.pulpproject.org/pulp_container/>`_.
* `Pulp Ansible plugin <https://docs.pulpproject.org/pulp_ansible/>`_.
* `Pulp Debian plugin <https://docs.pulpproject.org/pulp_deb/>`_.
* `Pulp Python plugin <https://docs.pulpproject.org/pulp_python/>`_.
* `Pulp Chef Cookbook plugin <https://github.com/pulp/pulp_cookbook/blob/master/README.rst/>`_.
* `Pulp Maven plugin <https://docs.pulpproject.org/pulp_maven/>`_.
* `Ansible GalaxyNG plugin <https://github.com/ansible/galaxy_ng/blob/master/README.md/>`_.
* `Pulp Certguard plugin <https://docs.pulpproject.org/certguard/>`_.
* `Pulp 2-to-3 Migration plugin <https://docs.pulpproject.org/pulp_2to3_migration/>`_.


And don't hesitate to :ref:`contact us<community>` with any questions during development.
Let us know when the plugin is ready and we will be happy to add it to the list of available plugins for Pulp!

.. note::
   Are we missing a plugin? Let us know via the pulp-dev@redhat.com mailing list.


.. _Plugin API:

Plugin API
==========

The Pulp Plugin API is published and versioned with ``pulpcore``. It is governed by our `deprecation
policy <_deprecation_policy>`_.

Plugin Writer's Guide
---------------------
.. toctree::
   plugin-writer/index

Plugin Writer's Reference
-------------------------
.. toctree::
   :maxdepth: 1

   reference/index

Plugin API Reference
--------------------
.. toctree::
   api-reference/index
