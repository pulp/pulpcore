from django.db import models

from pulpcore.app.models import BaseModel

MIGRATION_STATUS_CHOICES = (
    ("pending", "Pending"),
    ("running", "Running"),
    ("complete", "Complete"),
    ("failed", "Failed"),
)


class MigrationStatus(BaseModel):
    database_alias = models.TextField(unique=True)
    status = models.TextField(choices=MIGRATION_STATUS_CHOICES, default="pending")
    completed_at = models.DateTimeField(null=True)
    error = models.TextField(null=True)

    class Meta:
        verbose_name_plural = "migration statuses"
