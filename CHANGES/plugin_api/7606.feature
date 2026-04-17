Added a `publish` parameter to the repository modify endpoint and the `add_and_remove` task.
Plugins can opt in by accepting `publish` in their `on_new_version` override or custom
`modify_task`. The `RepositoryVersion` context manager will pass `publish=True` to
`on_new_version` if the plugin's method signature supports it.
