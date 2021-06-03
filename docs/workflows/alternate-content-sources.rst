Alternate Content Sources
=========================

.. warning:: This feature require plugin support to work correctly.

Overview
--------

Pulp supports the concept of Alternate Content Sources which sync content using
a Remote.  Each content source is a potential alternate provider of files that
are associated with content units in Pulp.  The next time Pulp needs to
download a file associated with a content unit, it searches ACSes for alternate
sources.

Create an Alternate Content Source
----------------------------------

To create an ACS you will need to create a Remote (with the "on_demand" policy)
with a base path of your Alternate Content Source.

.. code-block::

    http --form POST :24817/pulp/api/v3/acs/<plugin_name>/<content_type>/ remote=<remote_pulp_href> paths='["directory/", "folder/"]'

The ``paths`` parameter is optional. If a path is not provided, the base path
of your remote is used to search for content.

.. note::

    If no paths are specified, base address of your ACS remote will be used.

Update an Alternative Content Source
------------------------------------

To update an ACS, use a similar call to your ACS but with ``patch`` method:

.. code-block::

    http --form PATCH :24817/pulp/api/v3/acs/<plugin_name>/<content_type>/<acs_uuid>/ paths='["<path>"]' remote=<remote> name=<name>

Refresh
-------

To make the ACS available the next time you sync, you will need to call
``refresh`` endpoint.  It will go through your paths and catalog content from
your content source.

.. code-block::

    http --form POST :24817/pulp/api/v3/acs/<plugin_name>/<content_type>/<acs_uuid>/refresh/
