"""
Historical record of `move-domain` runs (Phase 2, Strategy A -- "Read-Only Cutover").

Purely operational bookkeeping, always on `default`: fleet-management metadata about *when* and
*between which aliases* a domain moved, not data belonging to any one domain. Gives an operator
something concrete to consult during the design doc's Step 6 "Monitoring" window (there is no
real monitoring/alerting infra in this implementation pass -- see the design doc and
`architecture/domain-db-offloading-runbook.md` -- this is just a durable timestamped record, not
a substitute for it) and lets `cleanup-moved-domain` refuse to run before `monitoring_until` has
elapsed.
"""

from django.db import models

from pulpcore.app.models import BaseModel

DOMAIN_MOVE_STATUS_CHOICES = (
    ("in_progress", "In Progress"),
    ("completed", "Completed"),
    ("failed", "Failed"),
    ("cleaned_up", "Cleaned Up"),
)


class DomainMove(BaseModel):
    """
    One row per `move-domain` invocation for a given `Domain`.

    Fields:
        domain (models.ForeignKey): The domain that was (or is being) moved.
        from_alias (models.SlugField): The `DATABASES` alias the domain's data-plane objects
            were moved from.
        to_alias (models.SlugField): The `DATABASES` alias the domain's data-plane objects were
            moved to.
        started_at (models.DateTimeField): When this move began (`Domain.moving` set to `True`).
        cutover_at (models.DateTimeField): When `Domain.database_alias` was updated to
            `to_alias` (Step 5 -- null until the move reaches cutover).
        monitoring_until (models.DateTimeField): End of the recommended Step 6 monitoring
            window (default 7 days after `cutover_at`; see `move-domain --monitoring-days`).
            `cleanup-moved-domain` warns (but does not block, since the operator is the one
            asserting the move looks healthy) if run before this.
        cleaned_up_at (models.DateTimeField): When `cleanup-moved-domain` deleted the stale rows
            from `from_alias` (Step 7 -- null until cleanup has run).
        status (models.TextField): One of "in_progress", "completed", "failed", "cleaned_up".
        error (models.TextField): Error message if `status` is "failed".
    """

    domain = models.ForeignKey("Domain", on_delete=models.CASCADE, related_name="moves")
    from_alias = models.SlugField()
    to_alias = models.SlugField()
    started_at = models.DateTimeField()
    cutover_at = models.DateTimeField(null=True)
    monitoring_until = models.DateTimeField(null=True)
    cleaned_up_at = models.DateTimeField(null=True)
    status = models.TextField(choices=DOMAIN_MOVE_STATUS_CHOICES, default="in_progress")
    error = models.TextField(null=True)

    class Meta:
        ordering = ["-pulp_created"]
