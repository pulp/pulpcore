Pulp Documentation
==================

This documentation is for `pulpcore`, which is used with plugins to fetch, upload, and organize
arbitrary content types.

Anyone interested in writing a plugin should reference the :ref:`Plugin API`.

.. _community:

Support
-------

If you need help with Pulp and cannot find the answer to your question in our docs, we encourage you
to check out our `help page at pulpproject.org <https://pulpproject.org/help/>`_ which includes
information about our mailing lists, IRC, etc.


Contributing
------------

Pulp is a free and open source software (FOSS) project and if you'd like to contribute, please check
out our :doc:`contributing docs<contributing/index>`.

Source code
^^^^^^^^^^^

  * `pulp Github organization <https://github.com/pulp/>`_
  * `pulpcore <https://github.com/pulp/pulpcore/>`_
  * `plugin repositories <https://pulpproject.org/content-plugins/>`_


How to Navigate the pulpcore and plugin docs
--------------------------------------------

Plugin Documentation
^^^^^^^^^^^^^^^^^^^^

If you are a new user who is evaluating Pulp it is recommended that you skim the documentation for
the plugins that add the content types you are interested in. Links to these docs can be found in
our `list of plugins <https://pulpproject.org/content-plugins/>`_

Pulpcore Documentation
^^^^^^^^^^^^^^^^^^^^^^

`pulpcore` handles some parts of common content management workflows, including high performance
downloading, task queuing with scalable workers, and management of content within versioned
repositories. Information about :ref:`installation`, :ref:`deployment`, and :doc:`general concepts
and terminology<concepts>` are all covered by the ``pulpcore`` documentation.


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
   versioning
