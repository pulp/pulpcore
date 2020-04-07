Added support for repairing a RepositoryVersion by redownloading corrupted artifact files.
Sending a POST request to
``/pulp/api/v3/repositories/<plugin>/<type>/<repository-uuid>/versions/<version-number>/repair/``
will trigger a task that scans all associated artfacts and attempts to fetch missing or corrupted ones again.
