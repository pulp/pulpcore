Plugins
=======

Plugins add support for a type of content to Pulp. For example, the
`file_plugin <https://github.com/pulp/pulp_file>`_ adds support for Pulp to manage files.

For a list of plugins check out our `list of plugins for Pulp 3 <https://pulpproject.org/pulp-3-plugins/>`_.

And don't hesitate to :ref:`contact us<community>` with any questions during development.
Let us know when the plugin is ready and we will be happy to add it to the list of available plugins for Pulp!

.. note::
   Are we missing a plugin? Let us know via the pulp-dev@redhat.com mailing list.

Plugin API
==========

The Pulp Plugin API is versioned separately from Pulp Core. It is governed by `semantic
versioning <http://semver.org/>`_. Backwards incompatible changes may be made until the
Plugin API reaches stability with v1.0.

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
