The file repository now supports the `publish` parameter on the modify endpoint. When
`publish=True` is passed, the repository version will be published after modification even if
`autopublish` is not enabled on the repository. Publication parameters configured on the
repository (e.g. `manifest`) will be used when publishing.
