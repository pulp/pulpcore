.. _planning-guide:

Plugin Planning Guide
=====================

This guide assumes that you are familiar with `general pulp concepts
<https://docs.pulpproject.org/plugins/plugin-writer/concepts/>`_.  Usually, the most difficult part
of writing a new plugin is understanding the ecosystem surrounding the content type(s) that you
want to support.

This page outlines some of the questions a plugin writer should consider while planning and writing
a new plugin.

What APIs are available from remote repositories?
-------------------------------------------------

Since remote repositories typically exist to serve content to a client, they usually implement a
web API. It is very helpful to become familiar with this interface in order to understand how
to fetch content into Pulp and subsequently distribute it to the client.

Some ecosystems have extensive APIs, so it is helpful to understand a general flow to narrow the
research scope. For sychronization, Pulp mimics the behavior of the client, and for
publishing/distributing, Pulp mimics the behavior of the server.

1. Discover content in a remote repository
2. Retrieve metadata about the content
3. Retrieve files

What does the metadata look like?
---------------------------------

Understanding the structure and content of a content type's metadata is crucial to the design and
function of a plugin.

**Example:**
When the Container plugin was in the planning phase, engineers got familiar with the `manifest spec
files <https://docs.docker.com/registry/spec/manifest-v2-2/>`_ to understand how to properly design
the workflow of Container content management within the plugin.


Which data should be modeled as Content Units?
----------------------------------------------

Will this data be added to/removed from a repository individually? If yes, this data could be a
Content Unit.

Should it be possible to add/remove a subset of this data to a repository? If yes, you should
consider managing this as a smaller unit.
