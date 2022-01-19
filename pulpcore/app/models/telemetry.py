import uuid

from django.db import models

from django_lifecycle import hook, LifecycleModel


class SystemID(LifecycleModel):
    pulp_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    @hook("before_save")
    def ensure_singleton(self):
        if SystemID.objects.exists():
            raise RuntimeError("This system already has a SystemID")

    class Meta:
        ordering = ("pulp_id",)
