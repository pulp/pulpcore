Concepts and Terminology
========================

This introduction presents a high level overview of Pulp terminology and concepts. It is designed
to be understandable to anyone who is familiar with software management even without prior
knowledge of Pulp. This document favors clarity and accuracy over ease of reading.

From a user’s perspective Pulp is a tool to manage their content. In this context, “Pulp” refers to
“pulpcore and one or more plugins”. Because of its dependent relationship with plugins, pulpcore
can be described as a framework for plugin development.

:term:`pulpcore` is a generalized backend with a REST API and a plugin API. Users will need at
least one :term:`plugin` to manage :term:`Content`.  Each :term:`type` of content unit (like rpm or
deb) is defined by a plugin.  Files that belong to a content unit are called
:term:`Artifacts<Artifact>`. Each content unit can have 0 or many artifacts and artifacts can be
shared by multiple content units.

.. image:: ./_diagrams/concept-content.png
    :align: center

Content units in Pulp are organized by their membership in :term:`Repositories<Repository>` over
time. Plugin users can add or remove content units to a repository. Each time the content set of a
repository is changed, a new :term:`RepositoryVersion` is created. Any operation such as sync that
doesn't result in a change of the content set will not produce a new repository version.

.. image:: ./_diagrams/concept-repository.png
    :align: center
.. image:: ./_diagrams/concept-add-repo.png
    :align: center

Users can inform Pulp about external sources of content units, called :term:`Remotes<Remote>`.
Plugins can define actions to interact with those sources. For example, most or all plugins define
:term:`sync` to fetch content units from a remote and add them to a repository.

.. image:: ./_diagrams/concept-remote.png
    :align: center

All content that is managed by Pulp can be hosted by the :term:`content app`. Users create
a :term:`Publication` for a content set in a repository version. A publication consists of the
metadata of the content set and the artifacts of each content unit in the content set. To host a
publication, it must be assigned to a :term:`Distribution`, which determines how and where a
publication is served.

.. image:: ./_diagrams/concept-publish.png
    :align: center
