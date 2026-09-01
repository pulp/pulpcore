from django.db import models

from pulpcore.app.models import BaseModel

DOMAIN_MOVE_STATUS_CHOICES = (
    ("in_progress", "In Progress"),
    ("completed", "Completed"),
    ("failed", "Failed"),
    ("cleaned_up", "Cleaned Up"),
)


class DomainMove(BaseModel):
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
