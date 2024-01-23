(stages-api-docs)=

# pulpcore.plugin.stages

Plugin writers can use the Stages API to create a high-performance, download-and-saving pipeline
to make writing sync code easier. There are several parts to the API:

1. {ref}`declarative-version` is a generic pipeline useful for most synchronization use cases.
2. The builtin Stages including {ref}`artifact-stages` and {ref}`content-stages`.
3. The {ref}`stages-api`, which allows you to build custom stages and pipelines.

(declarative-version)=

## DeclarativeVersion

```{eval-rst}
.. autoclass:: pulpcore.plugin.stages.DeclarativeVersion
```

```{eval-rst}
.. autoclass:: pulpcore.plugin.stages.DeclarativeArtifact
   :no-members:
```

```{eval-rst}
.. autoclass:: pulpcore.plugin.stages.DeclarativeContent
   :no-members:
   :members: resolution

```

(stages-api)=

## Stages API

```{eval-rst}
.. autofunction:: pulpcore.plugin.stages.create_pipeline
```

```{eval-rst}
.. autoclass:: pulpcore.plugin.stages.Stage
   :special-members: __call__
```

```{eval-rst}
.. autoclass:: pulpcore.plugin.stages.EndStage
   :special-members: __call__

```

(artifact-stages)=

## Artifact Related Stages

```{eval-rst}
.. autoclass:: pulpcore.plugin.stages.ArtifactDownloader
```

```{eval-rst}
.. autoclass:: pulpcore.plugin.stages.ArtifactSaver
```

```{eval-rst}
.. autoclass:: pulpcore.plugin.stages.RemoteArtifactSaver
```

```{eval-rst}
.. autoclass:: pulpcore.plugin.stages.QueryExistingArtifacts

```

(content-stages)=

## Content Related Stages

```{eval-rst}
.. autoclass:: pulpcore.plugin.stages.ContentSaver
   :private-members: _pre_save, _post_save
```

```{eval-rst}
.. autoclass:: pulpcore.plugin.stages.QueryExistingContents
```

```{eval-rst}
.. autoclass:: pulpcore.plugin.stages.ResolveContentFutures
```

```{eval-rst}
.. autoclass:: pulpcore.plugin.stages.ContentAssociation
```
