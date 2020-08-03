from import_export import resources


class QueryModelResource(resources.ModelResource):
    """
    A ModelResource that knows the RepositoryVersion to use to filter its query

    QueryModelResource has-a repository-version that can be used to limit its export, and a
    queryset that is derived from that repository-version.

    A plugin-writer will subclass their ModelResources from QueryModelResource,
    and use it to define the limiting query

    Attributes:

        repo_version (models.RepositoryVersion): The RepositoryVersion whose content we would like
            to export
        queryset (django.db.models.query.QuerySet): filtering queryset for this resource
            (driven by repo_version)
    """

    def set_up_queryset(self):
        return None

    def __init__(self, repo_version=None):
        self.repo_version = repo_version
        if repo_version:
            self.queryset = self.set_up_queryset()

    class Meta:
        exclude = ("pulp_id", "pulp_created", "pulp_last_updated")


class BaseContentResource(QueryModelResource):
    """
    A QueryModelResource that knows how to fill in the 'upstream_id' export-field

    BaseContentResource knows to de/hydrate upstream_id with the content-being-exported's pulp_id.

    All Content-based resources being import/exported should subclass from this class.
    """

    # An optional mapping that maps Content to Repositories. Useful when Content is sometimes not
    # tied directly to a Repository but rather to a subrepo. Formatting:
    #
    #     {"<repo name>": ["<content upstream_id>", "..."]}
    #
    content_mapping = None

    class Meta:
        exclude = QueryModelResource.Meta.exclude + ("_artifacts", "content", "content_ptr")

    def dehydrate_upstream_id(self, content):
        return str(content.pulp_id)
