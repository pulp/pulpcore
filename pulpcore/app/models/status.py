"""
Django models related to the Status API
"""

from datetime import timedelta

from django.conf import settings
from django.contrib.postgres.fields import HStoreField
from django.contrib.postgres.functions import TransactionNow
from django.db import models
from django.db.models import F, Value
from django.utils import timezone

from pulpcore.app.models import BaseModel


class AppStatusManager(models.Manager):
    _APP_TTL = {
        "api": settings.API_APP_TTL,
        "content": settings.CONTENT_APP_TTL,
        "worker": settings.WORKER_TTL,
    }

    def __init__(self):
        super().__init__()
        self._current_app_status = None

    def create(self, app_type, **kwargs):
        if self._current_app_status is not None:
            raise RuntimeError("There is already an app status in this process.")

        kwargs.setdefault("ttl", timedelta(seconds=self._APP_TTL[app_type]))
        obj = super().create(app_type=app_type, **kwargs)
        self._current_app_status = obj
        return obj

    async def acreate(self, app_type, **kwargs):
        if self._current_app_status is not None:
            raise RuntimeError("There is already an app status in this process.")

        kwargs.setdefault("ttl", timedelta(seconds=self._APP_TTL[app_type]))
        obj = await super().acreate(app_type=app_type, **kwargs)
        self._current_app_status = obj
        return obj

    def current(self):
        if self._current_app_status is None:
            raise RuntimeError("There is no current app status.")
        return self._current_app_status

    def online(self):
        """
        Returns a queryset of objects that are online.
        """
        return self.filter(last_heartbeat__gte=TransactionNow() - F("ttl"))

    def missing(self):
        """
        Returns a queryset of workers that are missing.
        """
        return self.filter(last_heartbeat__lt=TransactionNow() - F("ttl"))

    def older_than(self, age):
        """
        Returns a queryset of workers that are older than age.
        """
        return self.filter(last_heartbeat__lt=TransactionNow() - Value(age))


class AppStatus(BaseModel):
    APP_TYPES = [
        ("api", "api"),
        ("content", "content"),
        ("worker", "worker"),
    ]
    objects = AppStatusManager()

    app_type = models.CharField(max_length=10, choices=APP_TYPES)
    name = models.TextField()
    versions = HStoreField(default=dict)
    ttl = models.DurationField(null=False)
    last_heartbeat = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return f"<{self.__class__.__name__}[{self.app_type}] {self.name}>"

    @property
    def online(self) -> bool:
        """
        To be considered 'online', an app must have a timestamp more recent than ``self.ttl``.
        """
        age_threshold = timezone.now() - self.ttl
        return self.last_heartbeat >= age_threshold

    @property
    def missing(self) -> bool:
        """
        Whether an app can be considered 'missing'

        To be considered 'missing', an App must have a timestamp older than ``self.ttl``.

        Returns:
            bool: True if the app is considered missing, otherwise False
        """
        return not self.online

    def save_heartbeat(self) -> None:
        """
        Update the last_heartbeat field to now and save it.

        Only the last_heartbeat field will be saved. No other changes will be saved.

        Raises:
            ValueError: When the model instance has never been saved before. This method can
                only update an existing database record.
        """
        self.save(update_fields=["last_heartbeat"])

    async def asave_heartbeat(self) -> None:
        """
        Update the last_heartbeat field to now and save it.

        Only the last_heartbeat field will be saved. No other changes will be saved.

        Raises:
            ValueError: When the model instance has never been saved before. This method can
                only update an existing database record.
        """
        await self.asave(update_fields=["last_heartbeat"])

    @property
    def current_task(self):
        """
        The task this worker is currently executing, if any.
        """
        return self.tasks.filter(state="running").first()
