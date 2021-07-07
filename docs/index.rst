Pulp Documentation
==================

This is the main landing page for documentation related to Pulp.

The documentation itself is broken into sub categories that provide more granular information and
workflows.

`pulpcore` handles some parts of common content management workflows, including high performance
downloading, task queuing with scalable workers, and management of content within versioned
repositories.

If you are looking for a very high-level overview of Pulp's features, check out `features page at
pulpproject.org <https://pulpproject.org/features/>`_

If you want an overview of the main concepts and terminology of Pulp, see :doc:`Concepts and Terminology<concepts>`

If you want to understand the core workflows, see  :doc:`Workflows<workflows/index>`

If you want to look at the considerations and requirements for installing Pulp, see
 :ref:`installation`. If you want to evaluate Pulp quickly, try `Pulp in One
 Container <https://pulpproject.org/pulp-in-one-container/>`_

If you're looking for documentation specific to a content type, see :doc:`List of Plugins<plugins/index>`

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

Found a security issue?
-----------------------

If you find a security issue or have a security concern, see the :ref:`security-bugs` section for information about how to file a report.


Source code
^^^^^^^^^^^

  * `pulp Github organization <https://github.com/pulp/>`_
  * `pulpcore <https://github.com/pulp/pulpcore/>`_
  * `plugin repositories <https://pulpproject.org/content-plugins/>`_



Table of Contents
-----------------

.. toctree::
   :maxdepth: 2

   concepts
   from-pulp-2
   components
   installation/index
   configuration/index
   authentication/index
   workflows/index
   plugins/index
   rest_api
   client_bindings
   contributing/index
   bugs-features
   glossary
   changes
   versioning
