Added ability for plugins to dispatch a task to add pull-through content to an associated repository.

Add the class var `PULL_THROUGH_SUPPORTED = True` to the plugin's repository model to enable this
feature. Plugins can also customize the dispatched task by supplying their own
`pull_through_add_content` method on their repository model.
