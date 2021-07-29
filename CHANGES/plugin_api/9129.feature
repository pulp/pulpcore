`pulpcore.plugin.models.ProgressReport` now has async interfaces: asave(), aincrease_by(),
aincrement(), __aenter__(), _aexit__(). Plugins should switch to the async interfaces in their
Stages. 
`pulpcore.plugin.sync.sync_to_async_iterator` is a utility method to synchronize the database
queries generated when a QuerySet is iterated. 
