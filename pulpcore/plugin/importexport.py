from import_export import resources
from pulpcore.app.util import get_domain_pk


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

    def before_import_row(self, row, **kwargs):
        """
        Sets pulp_domain/_pulp_domain to the current-domain on import.
        Args:
            row (tablib.Dataset row): incoming import-row representing a single Variant.
            kwargs: args passed along from the import() call.
        """
        # There is probably a more pythonic/elegant way to do the following - but I am deliberately
        # opting for "verbose but COMPLETELY CLEAR" here.
        if "_pulp_domain" in row:
            row["_pulp_domain"] = get_domain_pk()

        if "pulp_domain" in row:
            row["pulp_domain"] = get_domain_pk()

    def set_up_queryset(self):
        return None

    def dehydrate_pulp_domain(self, content):
        return str(content.pulp_domain_id)

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

    def dehydrate_upstream_id(self, content):
        return str(content.pulp_id)

    class Meta:
        exclude = QueryModelResource.Meta.exclude + (
            "_artifacts",
            "content",
            "content_ptr",
            "timestamp_of_interest",
        )
