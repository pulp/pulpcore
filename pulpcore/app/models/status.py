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
    # This should be replaced with 3.87.
    def online(self):
        """
        Returns a queryset of objects that are online.

        To be considered 'online', a AppStatus must have a heartbeat timestamp within
        ``self.model.APP_TTL`` from now.

        Returns:
            [django.db.models.query.QuerySet][]:  A query set of the
                objects which are considered 'online'.
        """
        age_threshold = timezone.now() - self.model.APP_TTL
        return self.filter(last_heartbeat__gte=age_threshold)

    def missing(self, age=None):
        """
        Returns a queryset of workers meeting the criteria to be considered 'missing'

        To be considered missing, a AppsStatus must have a stale timestamp.  By default, stale is
        defined here as longer than the ``self.model.APP_TTL``, or you can specify age as a
        timedelta.

        Args:
            age (datetime.timedelta): Objects who have heartbeats older than this time interval are
                considered missing.

        Returns:
            [django.db.models.query.QuerySet][]:  A query set of the objects objects which
                are considered to be 'missing'.
        """
        age_threshold = timezone.now() - (age or self.model.APP_TTL)
        return self.filter(last_heartbeat__lt=age_threshold)


class _AppStatusManager(AppStatusManager):
    # This is an intermediate class in order to allow a ZDU.
    # It should be made the real thing with 3.87.
    def __init__(self):
        super().__init__()
        self._current_app_status = None

    def create(self, app_type, **kwargs):
        if self._current_app_status is not None:
            raise RuntimeError("There is already an app status in this process.")

        if app_type == "api":
            old_obj = ApiAppStatus.objects.create(**kwargs)
        elif app_type == "worker":
            from pulpcore.app.models import Worker

            old_obj = Worker.objects.create(**kwargs)
        else:
            raise NotImplementedError(f"Invalid app_type: {app_type}")
        obj = super().create(app_type=app_type, **kwargs)
        obj._old_status = old_obj
        self._current_app_status = obj
        return obj

    async def acreate(self, app_type, **kwargs):
        if self._current_app_status is not None:
            raise RuntimeError("There is already an app status in this process.")

        if app_type == "content":
            old_obj = await ContentAppStatus.objects.acreate(**kwargs)
        else:
            raise NotImplementedError(f"Invalid app_type: {app_type}")
        obj = await super().acreate(app_type=app_type, **kwargs)
        obj._old_status = old_obj
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
    _APP_TTL = {
        "api": settings.API_APP_TTL,
        "content": settings.CONTENT_APP_TTL,
        "worker": settings.WORKER_TTL,
    }
    objects = _AppStatusManager()

    app_type = models.CharField(max_length=10, choices=APP_TYPES)
    name = models.TextField(db_index=True, unique=True)
    versions = HStoreField(default=dict)
    ttl = models.DurationField(null=False)
    last_heartbeat = models.DateTimeField(auto_now=True)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.ttl = timedelta(seconds=self._APP_TTL[self.app_type])
        self._old_status = None

    def delete(self, *args, **kwargs):
        # adelete will call into this, so we should not replicate that one here.
        if self._old_status is not None:
            self._old_status.delete(*args, **kwargs)
        super().delete(*args, **kwargs)

    @property
    def online(self) -> bool:
        """
        To be considered 'online', an app must have a timestamp more recent than ``self.ttl``.
        """
        age_threshold = timezone.now() - self.ttl
        return self.last_heartbeat >= age_threshold

    @property
    def missing(self):
        """
        Whether an app can be considered 'missing'

        To be considered 'missing', an App must have a timestamp older than ``self.ttl``.

        Returns:
            bool: True if the app is considered missing, otherwise False
        """
        return not self.online

    def save_heartbeat(self):
        """
        Update the last_heartbeat field to now and save it.

        Only the last_heartbeat field will be saved. No other changes will be saved.

        Raises:
            ValueError: When the model instance has never been saved before. This method can
                only update an existing database record.
        """
        self._old_status.save_heartbeat()
        self.save(update_fields=["last_heartbeat"])

    async def asave_heartbeat(self):
        """
        Update the last_heartbeat field to now and save it.

        Only the last_heartbeat field will be saved. No other changes will be saved.

        Raises:
            ValueError: When the model instance has never been saved before. This method can
                only update an existing database record.
        """
        await self._old_status.asave_heartbeat()
        await self.asave(update_fields=["last_heartbeat"])

    @property
    def current_task(self):
        """
        The task this worker is currently executing, if any.
        """
        return self.tasks.filter(state="running").first()


class BaseAppStatus(BaseModel):
    """
    Represents an AppStatus.
    Deprecated, to be removed with 3.87.

    This class is abstract. Subclasses must define `APP_TTL` as a `timedelta`.

    Fields:

        name (models.TextField): The name of the app.
        last_heartbeat (models.DateTimeField): A timestamp of this worker's last heartbeat.
        versions (HStoreField): A dictionary with versions of all pulp components.
    """

    objects = AppStatusManager()

    name = models.TextField(db_index=True, unique=True)
    last_heartbeat = models.DateTimeField(auto_now=True)
    versions = HStoreField(default=dict)

    @property
    def online(self):
        """
        Whether an app can be considered 'online'

        To be considered 'online', an app must have a timestamp more recent than ``self.APP_TTL``.

        Returns:
            bool: True if the app is considered online, otherwise False
        """
        age_threshold = timezone.now() - self.APP_TTL
        return self.last_heartbeat >= age_threshold

    @property
    def missing(self):
        """
        Whether an app can be considered 'missing'

        To be considered 'missing', an App must have a timestamp older than ``self.APP_TTL``.

        Returns:
            bool: True if the app is considered missing, otherwise False
        """
        return not self.online

    def save_heartbeat(self):
        """
        Update the last_heartbeat field to now and save it.

        Only the last_heartbeat field will be saved. No other changes will be saved.

        Raises:
            ValueError: When the model instance has never been saved before. This method can
                only update an existing database record.
        """
        self.save(update_fields=["last_heartbeat"])

    async def asave_heartbeat(self):
        """
        Update the last_heartbeat field to now and save it.

        Only the last_heartbeat field will be saved. No other changes will be saved.

        Raises:
            ValueError: When the model instance has never been saved before. This method can
                only update an existing database record.
        """
        await self.asave(update_fields=["last_heartbeat"])

    class Meta:
        abstract = True


class ApiAppStatus(BaseAppStatus):
    """
    Represents a Api App Status
    Deprecated, to be removed with 3.87.
    """

    APP_TTL = timedelta(seconds=settings.API_APP_TTL)


class ContentAppStatus(BaseAppStatus):
    """
    Represents a Content App Status
    Deprecated, to be removed with 3.87.
    """

    APP_TTL = timedelta(seconds=settings.CONTENT_APP_TTL)
