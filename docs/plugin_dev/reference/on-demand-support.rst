.. _on-demand-support:

On-Demand Support
-----------------

"On-Demand support" refers to a plugin's ability to support downloading and creating Content but not
downloading their associated Artifacts. By convention, users expect the `Remote.policy` attribute to
determine when Artifacts will be downloaded. See the user docs for specifics on the user
expectations there.

.. _on-demand-support-with-da:

Adding Support when using DeclarativeVersion
============================================

Plugins like `pulp-file` sync content using `DeclarativeVersion`.
On-demand support can be added by specifying `deferred_download=True` at instantiation of
:class:`pulpcore.plugin.stages.DeclarativeArtifact`.

`Remote.policy` can take several values. To easily translate them, consider a snippet like this one
taken from `pulp-file`.::

    async def run(self):
        # Interpret download policy
        deferred_download = (self.remote.policy != Remote.IMMEDIATE)
        <...>
        da = DeclarativeArtifact(
            artifact=artifact,
            url=url,
            relative_path=relative_path,
            remote=self.remote,
            deferred_download=deferred_download,
        )
        <...>

.. hint::

   The `deferred_download` flag is used at the artifact level, to support on-demand concepts for
   plugins that need some artifacts to download immediately in all cases.
   See also :ref:`multi-level-discovery`.


Adding Support when using a Custom Stages API Pipeline
======================================================

Plugins like `pulp-rpm` that sync content using a custom pipeline can enable on-demand support by
excluding the `QueryExistingArtifacts`, `ArtifactDownloader` and `ArtifactSaver` stages. Without
these stages included, no Artifact downloading will occur. Content unit saving will occur, which
will correctly create the on-demand content units.

`Remote.policy` can take several values. To easily maintain the pipeline consider a snippet like
this one inspired by `pulp-rpm`::

    download = (remote.policy == Remote.IMMEDIATE)  # Interpret policy to download Artifacts or not
    stages = [first_stage]
    if download:
        stages.extend([QueryExistingArtifacts(), ArtifactDownloader(), ArtifactSaver()])
    stages.extend(the_rest_of_the_pipeline)  # This adds the Content and Association Stages

.. warning::

   Skipping of those Stages does not work with :ref:`multi-level-discovery`.
   If you need some artifacts downloaded anyway, follow the example on
   :ref:on-demand-support-with-dv` and include the artifact stages in the custom pipeline.

.. hint::

   Consider to also exclude the `ResolveContentFutures` stage.

What if the Custom Pipeline Needs Artifact Downloading?
=======================================================

For example, `pulp-container` uses a custom Stages API Pipeline, and relies on Artifact downloading to
download metadata that is saved and stored as a Content unit. This metadata defines more Content
units to be created without downloading their corresponding Artifacts. The on-demand support for
this type needs to download Artifacts for those content types, but not others.

By specifying `deferred_download=False` in the `DeclarativeArtifact` regardless of the overall sync
policy, lazy downloading for that specific artifact can be prohibited.

.. hint::

   See also :ref:`on-demand-support-with-da`

How Does This Work at the Model Layer?
======================================

The presence of a `RemoteArtifact` is what allows the Pulp content app to fetch and serve that
Artifact on-demand. So a Content unit is on-demand if and only if:

1. It has a saved Content unit

2. A `ContentArtifact` for each `Artifact` is saved that the Content unit would have referenced.
   Note: the `ContentArtifact` is created in both on-demand and not on-demand cases.

3. Instead of creating and saving an `Artifact`, a `RemoteArtifact` is created. This contains any
   known digest or size information allowing for automatic validation when the `Artifact` is
   fetched.


How does the Content App work with this Model Layer?
====================================================

When a request for content arrives, it is matched against a `Distribution` and eventually against a
specific Artifact path, which actually matches against a `ContentArtifact` not an `Artifact`. If an
`Artifact` exists, it is served to the client. Otherwise a `RemoteArtifact` allows the `Artifact` to
be downloaded on-demand and served to the client.

If `remote.policy == Remote.ON_DEMAND` the Artifact is saved on the first download. This causes
future requests to serve the already-downloaded and validated Artifact.

.. note::
   In situations where multiple Remotes synced and provided the same `Content` unit, only one
   `Content` unit is created but many `RemoteArtifact` objects may be created. The Pulp Content app
   will try all `RemoteArtifact` objects that correspond with a `ContentArtifact`. It's possible an
   unexpected `Remote` could be used when fetching that equivalent `Content` unit. Similar warnings
   are in the user documentation on on-demand.
