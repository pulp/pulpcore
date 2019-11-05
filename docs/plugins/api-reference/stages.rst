.. _stages-api-docs:

pulpcore.plugin.stages
======================

Plugin writers can use the Stages API to create a high-performance, download-and-saving pipeline
to make writing sync code easier. There are several parts to the API:

1. :ref:`declarative-version` is a generic pipeline useful for most synchronization use cases.
2. The builtin Stages including :ref:`artifact-stages`, :ref:`content-stages`, and
   :ref:`content-association-stages`.
3. The :ref:`stages-api`, which allows you to build custom stages and pipelines.


.. _declarative-version:

DeclarativeVersion
^^^^^^^^^^^^^^^^^^

.. autoclass:: pulpcore.plugin.stages.DeclarativeVersion

.. autoclass:: pulpcore.plugin.stages.DeclarativeArtifact
   :no-members:

.. autoclass:: pulpcore.plugin.stages.DeclarativeContent
   :no-members:
   :members: resolution


.. _stages-api:

Stages API
^^^^^^^^^^

.. autofunction:: pulpcore.plugin.stages.create_pipeline

.. autoclass:: pulpcore.plugin.stages.Stage
   :special-members: __call__

.. autoclass:: pulpcore.plugin.stages.EndStage
   :special-members: __call__


.. _artifact-stages:

Artifact Related Stages
^^^^^^^^^^^^^^^^^^^^^^^

.. autoclass:: pulpcore.plugin.stages.ArtifactDownloader

.. autoclass:: pulpcore.plugin.stages.ArtifactSaver

.. autoclass:: pulpcore.plugin.stages.RemoteArtifactSaver

.. autoclass:: pulpcore.plugin.stages.QueryExistingArtifacts


.. _content-stages:

Content Related Stages
^^^^^^^^^^^^^^^^^^^^^^

.. autoclass:: pulpcore.plugin.stages.ContentSaver
   :private-members: _pre_save, _post_save

.. autoclass:: pulpcore.plugin.stages.QueryExistingContents

.. autoclass:: pulpcore.plugin.stages.ResolveContentFutures


.. _content-association-stages:

Content Association and Unassociation Stages
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. autoclass:: pulpcore.plugin.stages.ContentAssociation

.. autoclass:: pulpcore.plugin.stages.ContentUnassociation

