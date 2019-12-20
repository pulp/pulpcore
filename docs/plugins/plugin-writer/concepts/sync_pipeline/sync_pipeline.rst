.. _stages-concept-docs:

Synchronizing Repositories with the async-Pipeline
==================================================

To accomplish the steps outlined in :ref:`sync-docs` in an efficient way, pulp provides a high
level api to construct a pipeline of stages. Those stages work in parallel like an assembly line
using pythons `async` feature in combination with the `asyncio` library. Each stage takes
designated content units from an incoming queue of type :class:`asyncio.Queue` and performes an
individual task on them before passing them to the outgoing queue that is connected to the next
stage.

The anathomy of a stage is that it inherits :class:`pulpcore.plugin.stages.Stage` and overwrites
its asynchronous callback :meth:`run`.
In :meth:`run` it can retrieve incoming declarative content individually via the asynchronous
iterator :meth:`self.items` or in batches via :meth:`self.batches`.
It can pass on declarative content with :meth:`self.put`.

The sync pipeline is headed by a `first_stage`, that is supposed to download upstream metadata
and iterate over all upstream content references. For each such reference, it creates a
:class:`pulpcore.plugin.stages.DeclarativeContent` that contains a prefilled but unsaved instance
of a subclass of :class:`pulpcore.plugin.content.Content`, as well as a list of
:class:`pulpcore.plugin.stages.DeclarativeArtifact`. The latter combine an unsaved instance of
:class:`pulpcore.plugin.content.Artifact` with a url to retrieve it.
The :class:`pulpcore.plugin.stages.DeclarativeContent` objects, that describe, what a content will
look like when properly downloaded and saved to the database, are passed one by one to the next
pipeline stage.
The responsibility of providing this `first_stage` lies completely in the plugins domain, since
this is the part of the pipeline specific to the repository type.

The pulp plugin api provides the following stages which also comprise the default pipeline in the
following order:

   1. :class:`pulpcore.plugin.stages.QueryExistingContents`
   2. :class:`pulpcore.plugin.stages.QueryExistingArtifacts`
   3. :class:`pulpcore.plugin.stages.ArtifactDownloader`
   4. :class:`pulpcore.plugin.stages.ArtifactSaver`
   5. :class:`pulpcore.plugin.stages.ContentSaver`
   6. :class:`pulpcore.plugin.stages.RemoteArtifactSaver`
   7. :class:`pulpcore.plugin.stages.ResolveContentFutures`
   8. :class:`pulpcore.plugin.stages.ContentAssociation`

If the `mirror=True` optional parameter is passed to `DeclarativeVersion` the pipeline also runs
:class:`pulpcore.plugin.stages.ContentUnassociation` at the end.

On-demand synchronizing
-----------------------

See :ref:`on-demand-support`.

.. _multi-level-discovery:

Multiple level discovery
------------------------

Plugins like `pulp_deb` and `pulp_container` use content artifacts to enumerate more content.
To support this pattern, the declarative content allows to be associated with a
:class:`asyncio.Future`, that is resolved when the content reaches the
:class:`pulpcore.plugin.stages.ResolveContentFutures` stage.
By awaiting this Future, one can implement an informational back loop into earlier stages.

.. warning::

   In order to prevent deadlocks, be sure that you mark the declarative content with
   `does_batch=False`, and that you do not drop it without resolving the future.

.. hint::

   If you need downloaded artifacts of this content for further discovery, make sure to
   provide `deferred_download=False` to the
   :class:`pulpcore.plugin.stages.DeclarativeArtifact`.
