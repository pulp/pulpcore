"""
Repository related Django models.
"""
from django.db import models

from .base import MasterModel, BaseModel


class AlternateContentSource(MasterModel):
    """
    Alternate sources of content.

    Fields:

        name (models.TextField): The alternate content source name.
        last_refreshed (models.DateTimeField): Last refreshed date.
        url (models.TextField): URL of Alternate Content Source.

    Relations:

        remote (models.ForeignKeyField): Associated remote
    """

    TYPE = "acs"
    REMOTE_TYPES = []

    name = models.TextField(db_index=True, unique=True)
    last_refreshed = models.DateTimeField(null=True)
    remote = models.ForeignKey("Remote", null=True, on_delete=models.PROTECT)

    class Meta:
        verbose_name_plural = "acs"


class AlternateContentSourcePath(BaseModel):
    """
    Alternate sources of content.

    Fields:

        path (models.TextField): The alternate content source name.

    Relations:

        alternate_content_source (models.ForeignKeyField): Associated AlternateContentSource
        repository (models.ForeignKeyField): Associated repository
    """

    alternate_content_source = models.ForeignKey(
        "AlternateContentSource", null=True, on_delete=models.CASCADE, related_name="paths"
    )
    path = models.TextField(default=None)
    repository = models.ForeignKey("Repository", null=True, on_delete=models.CASCADE)

    class Meta:
        unique_together = ("alternate_content_source", "path")
