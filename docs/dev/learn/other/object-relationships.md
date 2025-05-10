# Object Relationships

There are models which are expected to be used in plugin implementation, so understanding what they
are designed for is useful for a plugin writer. Each model below has a link to its documentation
where its purpose, all attributes and relations are listed.

Here is a gist of how models are related to each other and what each model is responsible for.

- `pulpcore.app.models.Repository` contains `pulpcore.plugin.models.Content`.
    `pulpcore.plugin.models.RepositoryContent` is used to represent this relation.
- `pulpcore.plugin.models.Content` can have `pulpcore.plugin.models.Artifact`
    associated with it. `pulpcore.plugin.models.ContentArtifact` is used to represent this
    relation.
- `pulpcore.plugin.models.ContentArtifact` can have
    `pulpcore.plugin.models.RemoteArtifact` associated with it.
- `pulpcore.plugin.models.Artifact` is a file.
- `pulpcore.plugin.models.RemoteArtifact` contains information about
    `pulpcore.plugin.models.Artifact` from a remote source, including URL to perform
    download later at any point.
- `pulpcore.plugin.models.Remote` knows specifics of the plugin
    `pulpcore.plugin.models.Content` to put it into Pulp.
    `pulpcore.plugin.models.Remote` defines how to synchronize remote content. Pulp
    Platform provides support for concurrent `downloading <download-docs>` of remote content.
    Plugin writer is encouraged to use one of them but is not required to.
- `pulpcore.plugin.models.PublishedArtifact` refers to
    `pulpcore.plugin.models.ContentArtifact` which is published and belongs to a certain
    `pulpcore.app.models.Publication`.
- `pulpcore.plugin.models.PublishedMetadata` is a file generated while publishing and
    belongs to a certain `pulpcore.app.models.Publication`.
- `pulpcore.app.models.Publication` is a result of publish operation of a specific
    `pulpcore.plugin.models.RepositoryVersion`.
- `pulpcore.app.models.Distribution` defines how a publication is distributed for a specific
    `pulpcore.plugin.models.Publication`.
- `pulpcore.plugin.models.ProgressReport` is used to report progress of the task.
- `pulpcore.plugin.models.GroupProgressReport` is used to report progress of the task group.

An important feature of the current design is deduplication of
`pulpcore.plugin.models.Content` and `pulpcore.plugin.models.Artifact` data.
`pulpcore.plugin.models.Content` is shared between `pulpcore.app.models.Repository`,
`pulpcore.plugin.models.Artifact` is shared between
`pulpcore.plugin.models.Content`.
See more details on how it affects remote implementation in `define-remote` section.

Check `pulp_file` [implementation](https://github.com/pulp/pulpcore/tree/main/pulp_file) to see how all
those models are used in practice.
More detailed explanation of model usage with references to `pulp_file` code is below.
