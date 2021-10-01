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

    pulp <plugin_name> acs create --name <acs_name> --remote <remote> --path <path> --path <path>

.. note::

  The ``path`` option is optional and can be specified multiple times. If a path is not provided,
  the url of your remote is used to search for content.

Update an Alternate Content Source
----------------------------------

To update an ACS, use a similar call to your ACS but with ``update`` command:

.. code-block::

    pulp <plugin_name> acs update --name <acs_name> --remote <remote>

To add or remove paths, use the ``path`` subcommand:

.. code-block::

    pulp <plugin_name> acs path add --name <acs_name> --path <path>
    pulp <plugin_name> acs path remove --name <acs_name> --path <path>

Refresh
-------

To make the ACS available the next time you sync, you will need to call the ``refresh`` command.  It
will go through your paths and catalog content from your content source.

.. code-block::

    pulp <plugin_name> acs refresh --name <acs_name>
