from functools import lru_cache

from django.db import models

from django_lifecycle import hook, LifecycleModel

from pulpcore.app.models import pulp_uuid


class SystemID(LifecycleModel):
    pulp_id = models.UUIDField(primary_key=True, default=pulp_uuid, editable=False)

    @hook("before_save")
    def ensure_singleton(self):
        if SystemID.objects.exists():
            raise RuntimeError("This system already has a SystemID")

    class Meta:
        ordering = ("pulp_id",)


@lru_cache(maxsize=1)
def system_id():
    system_id_obj = SystemID.objects.first()
    return str(system_id_obj.pk)
