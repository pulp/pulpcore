Add a ``get_content`` method to ``pulpcore.plugin.models.RepositoryVersion`` that accepts a
queryset and returns a list of content in that repository using the given queryset.
This allows for specific content type to be returned by executing
``repo_version.get_content(content_qs=MyContentType.objects)``.
