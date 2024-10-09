# pulpcore.plugin.stages

Plugin writers can use the Stages API to create a high-performance, download-and-saving pipeline
to make writing sync code easier. There are several parts to the API:

1. `declarative-version` is a generic pipeline useful for most synchronization use cases.
2. The builtin Stages including `artifact-stages` and `content-stages`.
3. The `stages-api`, which allows you to build custom stages and pipelines.

## DeclarativeVersion

::: pulpcore.plugin.stages.DeclarativeVersion

::: pulpcore.plugin.stages.DeclarativeArtifact
    options:
        members: false

::: pulpcore.plugin.stages.DeclarativeContent
    options:
        members: false

## Stages API

::: pulpcore.plugin.stages.create_pipeline

::: pulpcore.plugin.stages.Stage

::: pulpcore.plugin.stages.EndStage

## Artifact Related Stages

::: pulpcore.plugin.stages.ArtifactDownloader

::: pulpcore.plugin.stages.ArtifactSaver

::: pulpcore.plugin.stages.RemoteArtifactSaver

::: pulpcore.plugin.stages.QueryExistingArtifacts

## Content Related Stages

::: pulpcore.plugin.stages.ContentSaver

::: pulpcore.plugin.stages.QueryExistingContents

::: pulpcore.plugin.stages.ResolveContentFutures

::: pulpcore.plugin.stages.ContentAssociation
