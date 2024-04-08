"""
Django models related to the Status API
"""

from datetime import timedelta

from django.conf import settings
from django.contrib.postgres.fields import HStoreField
from django.db import models
from django.utils import timezone

from pulpcore.app.models import BaseModel


class AppStatusManager(models.Manager):
    def online(self):
        """
        Returns a queryset of objects that are online.

        To be considered 'online', a AppStatus must have a heartbeat timestamp within
        ``self.model.APP_TTL`` from now.

        Returns:
            :class:`django.db.models.query.QuerySet`:  A query set of the
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
            :class:`django.db.models.query.QuerySet`:  A query set of the objects objects which
                are considered to be 'missing'.
        """
        age_threshold = timezone.now() - (age or self.model.APP_TTL)
        return self.filter(last_heartbeat__lt=age_threshold)


class BaseAppStatus(BaseModel):
    """
    Represents an AppStatus.

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

    class Meta:
        abstract = True


class ApiAppStatus(BaseAppStatus):
    """
    Represents a Api App Status
    """

    APP_TTL = timedelta(seconds=settings.API_APP_TTL)


class ContentAppStatus(BaseAppStatus):
    """
    Represents a Content App Status
    """

    APP_TTL = timedelta(seconds=settings.CONTENT_APP_TTL)
