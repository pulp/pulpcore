Alternate Content Sources
=========================

.. warning:: This feature requires plugin support to work correctly.

.. warning:: This feature is provided as a tech preview and could change in backwards incompatible
  ways in the future

Overview
--------

Pulp supports the concept of Alternate Content Sources which sync content using a Remote.  Each
content source is a potential alternate provider of files that are associated with content units in
Pulp.  The next time Pulp needs to download a file associated with a content unit, it searches ACSes
for alternate sources.

Create an Alternate Content Source
----------------------------------

To create an ACS, you'll need a Remote with the "on_demand" policy. You can have an ACS point to
multiple Repositories by specifying the ``paths`` parameter. Each path will be appended to the
Remote's url.

.. code-block::

    http POST :24817/pulp/api/v3/acs/<plugin_name>/<content_type>/ remote=<remote_pulp_href> paths:='["directory/", "folder/"]'

.. note::

  The ``paths`` parameter is optional. If a path is not provided, the url of your remote is used to
  search for content.

Update an Alternate Content Source
----------------------------------

To update an ACS, use a similar call to your ACS but with ``patch`` method:

.. code-block::

    http PATCH :24817/pulp/api/v3/acs/<plugin_name>/<content_type>/<acs_uuid>/ paths:='["<path>"]' remote=<remote> name=<name>

Refresh
-------

To make the ACS available the next time you sync, you will need to call ``refresh`` endpoint.  It
will go through your paths and catalog content from your content source.

.. code-block::

    http POST :24817/pulp/api/v3/acs/<plugin_name>/<content_type>/<acs_uuid>/refresh/
