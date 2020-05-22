from import_export import fields
from import_export.widgets import ForeignKeyWidget
from logging import getLogger

from pulpcore.app.models.content import (
    Artifact,
    Content,
    ContentArtifact,
)
from pulpcore.app.models.repository import Repository
from pulpcore.plugin.importexport import QueryModelResource


log = getLogger(__name__)


#
# Artifact and Repository are different from other import-export entities, in that they are not
# repo-version-specific.
#
class ArtifactResource(QueryModelResource):
    class Meta:
        model = Artifact
        exclude = (
            "pulp_id",
            "pulp_created",
            "pulp_last_updated",
        )
        import_id_fields = ("sha256",)


class RepositoryResource(QueryModelResource):
    class Meta:
        model = Repository
        import_id_fields = ("name",)
        exclude = (
            "pulp_id",
            "pulp_created",
            "pulp_last_updated",
            "content",
        )


class ContentArtifactResource(QueryModelResource):
    """
    Handles import/export of the ContentArtifact model.

    ContentArtifact is different from other import-export entities because it has no 'natural key'
    other than a pulp_id, which aren't shared across instances. We do some magic to link up
    ContentArtifacts to their matching (already-imported) Content.
    """

    artifact = fields.Field(
        column_name="artifact", attribute="artifact", widget=ForeignKeyWidget(Artifact, "sha256")
    )

    def before_import_row(self, row, **kwargs):
        """
        Fixes the content-ptr of an incoming content-artifact row at import time.

        Finds the 'original uuid' of the Content for this row, looks it up as the
        'upstream_id' of imported Content, and then replaces the Content-pk with its
        (new) uuid.

        Args:
            row (tablib.Dataset row): incoming import-row representing a single ContentArtifact.
            kwargs: args passed along from the import() call.

        Returns:
            (tablib.Dataset row): row that now points to the new downstream uuid for its content.
        """

        linked_content = Content.objects.get(upstream_id=row["content"])
        row["content"] = str(linked_content.pulp_id)

    def set_up_queryset(self):
        return ContentArtifact.objects.filter(content__in=self.repo_version.content)

    class Meta:
        model = ContentArtifact
        import_id_fields = (
            "content",
            "relative_path",
        )
        exclude = (
            "pulp_created",
            "pulp_last_updated",
            "_artifacts",
            "pulp_id",
        )
