Added new endpoint ``/pulp/api/v3/orphans/cleanup/``. When called with ``POST`` and no parameters
it is equivalent to calling ``DELETE /pulp/api/v3/orphans/``. Additionally the optional parameter
``content_hrefs`` can be specified and must contain a list of content hrefs. When ``content_hrefs``
is specified, only those content units will be considered to be removed by orphan cleanup.
