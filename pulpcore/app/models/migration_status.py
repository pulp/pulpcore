"""
Tracks the outcome of `migrate-all`'s per-alias `migrate` invocations (Phase 1).

Purely operational bookkeeping: gives an operator/the `/status/` endpoint a durable record of
which `DATABASES` alias is at which migration state, without needing to `showmigrations` every
alias individually. Always lives on `default` -- it is control-plane data about the fleet, not
data belonging to any one domain.
"""

from django.db import models

from pulpcore.app.models import BaseModel

MIGRATION_STATUS_CHOICES = (
    ("pending", "Pending"),
    ("running", "Running"),
    ("complete", "Complete"),
    ("failed", "Failed"),
)


class MigrationStatus(BaseModel):
    """
    Per-`DATABASES`-alias record of the last `migrate-all` outcome.

    Fields:
        database_alias (models.TextField): The `DATABASES` alias this row tracks. Unique --
            one row per alias, updated in place on every `migrate-all` run.
        status (models.TextField): One of "pending", "running", "complete", "failed".
        completed_at (models.DateTimeField): When this alias last reached "complete".
        error (models.TextField): The exception message from the most recent failed attempt,
            if any. Cleared out on the next successful run.
    """

    database_alias = models.TextField(unique=True)
    status = models.TextField(choices=MIGRATION_STATUS_CHOICES, default="pending")
    completed_at = models.DateTimeField(null=True)
    error = models.TextField(null=True)

    class Meta:
        verbose_name_plural = "migration statuses"
