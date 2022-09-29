.. _object-relationships:

Object Relationships
====================

There are models which are expected to be used in plugin implementation, so understanding what they
are designed for is useful for a plugin writer. Each model below has a link to its documentation
where its purpose, all attributes and relations are listed.

Here is a gist of how models are related to each other and what each model is responsible for.

* :class:`~pulpcore.app.models.Repository` contains :class:`~pulpcore.plugin.models.Content`.
  :class:`~pulpcore.plugin.models.RepositoryContent` is used to represent this relation.
* :class:`~pulpcore.plugin.models.Content` can have :class:`~pulpcore.plugin.models.Artifact`
  associated with it. :class:`~pulpcore.plugin.models.ContentArtifact` is used to represent this
  relation.
* :class:`~pulpcore.plugin.models.ContentArtifact` can have
  :class:`~pulpcore.plugin.models.RemoteArtifact` associated with it.
* :class:`~pulpcore.plugin.models.Artifact` is a file.
* :class:`~pulpcore.plugin.models.RemoteArtifact` contains information about
  :class:`~pulpcore.plugin.models.Artifact` from a remote source, including URL to perform
  download later at any point.
* :class:`~pulpcore.plugin.models.Remote` knows specifics of the plugin
  :class:`~pulpcore.plugin.models.Content` to put it into Pulp.
  :class:`~pulpcore.plugin.models.Remote` defines how to synchronize remote content. Pulp
  Platform provides support for concurrent  :ref:`downloading <download-docs>` of remote content.
  Plugin writer is encouraged to use one of them but is not required to.
* :class:`~pulpcore.plugin.models.PublishedArtifact` refers to
  :class:`~pulpcore.plugin.models.ContentArtifact` which is published and belongs to a certain
  :class:`~pulpcore.app.models.Publication`.
* :class:`~pulpcore.plugin.models.PublishedMetadata` is a file generated while publishing and
  belongs to a certain :class:`~pulpcore.app.models.Publication`.
* :class:`~pulpcore.app.models.Publication` is a result of publish operation of a specific
  :class:`~pulpcore.plugin.models.RepositoryVersion`.
* :class:`~pulpcore.app.models.Distribution` defines how a publication is distributed for a specific
  :class:`~pulpcore.plugin.models.Publication`.
* :class:`~pulpcore.plugin.models.ProgressReport` is used to report progress of the task.
* :class:`~pulpcore.plugin.models.GroupProgressReport` is used to report progress of the task group.


An important feature of the current design is deduplication of
:class:`~pulpcore.plugin.models.Content` and :class:`~pulpcore.plugin.models.Artifact` data.
:class:`~pulpcore.plugin.models.Content` is shared between :class:`~pulpcore.app.models.Repository`,
:class:`~pulpcore.plugin.models.Artifact` is shared between
:class:`~pulpcore.plugin.models.Content`.
See more details on how it affects remote implementation in :ref:`define-remote` section.


Check ``pulp_file`` `implementation <https://github.com/pulp/pulp_file/>`_ to see how all
those models are used in practice.
More detailed explanation of model usage with references to ``pulp_file`` code is below.


