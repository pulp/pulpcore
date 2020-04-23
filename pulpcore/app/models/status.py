"""
Django models related to the Status API
"""
from datetime import timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone

from pulpcore.app.models import BaseModel


class ContentAppStatusManager(models.Manager):
    def online(self):
        """
        Returns a queryset of ``ContentAppStatus`` objects that are online.

        To be considered 'online', a ContentAppStatus must have a heartbeat timestamp within
        ``settings.CONTENT_APP_TTL`` from now.

        Returns:
            :class:`django.db.models.query.QuerySet`:  A query set of the ``ContentAppStatus``
                objects which are considered 'online'.
        """
        now = timezone.now()
        age_threshold = now - timedelta(seconds=settings.CONTENT_APP_TTL)

        return self.filter(last_heartbeat__gte=age_threshold)


class ContentAppStatus(BaseModel):
    """
    Represents a Content App Status

    Fields:

        name (models.TextField): The name of the content app
        last_heartbeat (models.DateTimeField): A timestamp of this worker's last heartbeat
    """

    objects = ContentAppStatusManager()

    name = models.TextField(db_index=True, unique=True)
    last_heartbeat = models.DateTimeField(auto_now=True)

    @property
    def online(self):
        """
        Whether a content app can be considered 'online'

        To be considered 'online', a content app must have a heartbeat timestamp more recent than
        the ``CONTENT_APP_TTL`` setting.

        Returns:
            bool: True if the content app is considered online, otherwise False
        """
        now = timezone.now()
        age_threshold = now - timedelta(seconds=settings.CONTENT_APP_TTL)

        return self.last_heartbeat >= age_threshold

    @property
    def missing(self):
        """
        Whether a Content App can be considered 'missing'

        To be considered 'missing', a Content App must have a timestamp older than
        ``SETTINGS.CONTENT_APP_TTL``.

        Returns:
            bool: True if the content app is considered missing, otherwise False
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
