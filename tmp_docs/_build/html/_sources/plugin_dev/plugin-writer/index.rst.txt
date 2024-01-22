Plugin Writer's Guide
=====================

.. note::
   This documentation is for Pulp Plugin developers. For Pulp Core development, see the
   `our contributor docs <https://docs.pulpproject.org/contributing/>`_.

Pulp Core does not manage content by itself, but instead relies on plugins to add support for one
content type or another. Examples of content types include RPM packages, Ansible roles, and Container
images.

This documentation outlines how to create a Pulp plugin that provides features like:

* Define a new content type and its attributes
* Download and save the new type of content into Pulp Core
* Publish the new type of content, allowing Pulp Core to serve it at a ``distribution``
* Export content to remote servers or CDNs
* Add custom web application views
* Implement custom features, e.g. dependency solving, retension/deletion policies, etc.

Along with this guide, it may be useful to refer to to our simplest plugin, `pulp_file
<https://github.com/pulp/pulp_file/>`_.

Additionally we provide a `Plugin Template <https://github.com/pulp/plugin_template>`_ which will
take care of a majority of the boilerplate.

.. toctree::
   :maxdepth: 2

   planning-guide
   concepts/index
   plugin-walkthrough
