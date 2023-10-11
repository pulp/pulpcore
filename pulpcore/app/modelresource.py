from import_export import fields
from import_export.widgets import ForeignKeyWidget
from logging import getLogger

from pulpcore.app.models.content import (
    Artifact,
    Content,
    ContentArtifact,
)
from pulpcore.app.models.repository import Repository
from pulpcore.constants import ALL_KNOWN_CONTENT_CHECKSUMS
from pulpcore.plugin.importexport import QueryModelResource


log = getLogger(__name__)


#
# Artifact and Repository are different from other import-export entities, in that they are not
# repo-version-specific.
#
class ArtifactResource(QueryModelResource):
    """Resource for import/export of artifacts."""

    def before_import_row(self, row, **kwargs):
        """
        Sets digests to None if they are blank strings.

        Args:
            row (tablib.Dataset row): incoming import-row representing a single Variant.
            kwargs: args passed along from the import() call.

        """
        super().before_import_row(row, **kwargs)

        # the export converts None to blank strings but sha384 and sha512 have unique constraints
        # that get triggered if they are blank. convert checksums back into None if they are blank.
        for checksum in ALL_KNOWN_CONTENT_CHECKSUMS:
            if row[checksum] == "":
                row[checksum] = None

    class Meta:
        model = Artifact
        exclude = (
            "pulp_id",
            "pulp_created",
            "pulp_last_updated",
            "timestamp_of_interest",
        )
        import_id_fields = (
            "pulp_domain",
            "sha256",
        )


class RepositoryResource(QueryModelResource):
    class Meta:
        model = Repository
        import_id_fields = (
            "pulp_domain",
            "name",
        )
        exclude = (
            "pulp_id",
            "pulp_created",
            "pulp_last_updated",
            "content",
            "next_version",
            "repository_ptr",
            "remote",
            "pulp_labels",
        )


class ContentArtifactResource(QueryModelResource):
    """
    Handles import/export of the ContentArtifact model.

    ContentArtifact is different from other import-export entities because it has no 'natural key'
    other than a pulp_id, which aren't shared across instances. We do some magic to link up
    ContentArtifacts to their matching (already-imported) Content.

    Some plugin-models have sub-repositories. We take advantage of the content-mapping
    machinery to account for those contentartifacts as well.
    """

    artifact = fields.Field(
        column_name="artifact", attribute="artifact", widget=ForeignKeyWidget(Artifact, "sha256")
    )
    linked_content = {}

    def __init__(self, repo_version=None, content_mapping=None):
        self.content_mapping = content_mapping
        if not ContentArtifactResource.linked_content:
            ContentArtifactResource.linked_content = self.fetch_linked_content()
        super().__init__(repo_version)

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
        super().before_import_row(row, **kwargs)

        row["content"] = self.linked_content[row["content"]]

    def set_up_queryset(self):
        content_pks = set(self.repo_version.content.values_list("pk", flat=True))

        if self.content_mapping:
            for content_ids in self.content_mapping.values():
                content_pks |= set(content_ids)

        return (
            ContentArtifact.objects.filter(content__in=content_pks)
            .order_by("content", "relative_path")
            .select_related("artifact")
        )

    def dehydrate_content(self, content_artifact):
        return str(content_artifact.content_id)

    def fetch_linked_content(self):
        linked_content = {}
        c_qs = Content.objects.filter(upstream_id__isnull=False).values("upstream_id", "pulp_id")
        for c in c_qs.iterator():
            linked_content[str(c["upstream_id"])] = str(c["pulp_id"])

        return linked_content

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
