"""
Container for models using generic relations provided by Django's ContentTypes framework.

References:
    https://docs.djangoproject.com/en/3.2/ref/contrib/contenttypes/#generic-relations
"""

import logging

from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ObjectDoesNotExist
from django.db import models

from pulpcore.app.models.base import BaseModel

_logger = logging.getLogger(__name__)


_UNSET = object()

_DOMAIN_WALK_MAX_DEPTH = 2


def _resolve_domain_id(value, _depth=0, _seen=None):
    domain_id = getattr(value, "pulp_domain_id", None)
    if domain_id is not None:
        return domain_id
    if _depth >= _DOMAIN_WALK_MAX_DEPTH:
        return None
    if _seen is None:
        _seen = set()
    if value.pk is not None:
        key = (type(value), value.pk)
        if key in _seen:
            return None
        _seen.add(key)
    for field in value._meta.get_fields():
        if not (field.many_to_one or field.one_to_one) or not getattr(field, "concrete", False):
            continue
        try:
            related = getattr(value, field.name)
        except ObjectDoesNotExist:
            continue
        if related is None or not hasattr(related, "_meta"):
            continue
        resolved = _resolve_domain_id(related, _depth + 1, _seen)
        if resolved is not None:
            return resolved
    return None


class DomainResolvedGenericRelation:
    def __init__(self, *args, **kwargs):
        has_content_object = "content_object" in kwargs
        content_object = kwargs.pop("content_object", None)
        super().__init__(*args, **kwargs)
        if has_content_object:
            self.content_object = content_object

    @property
    def content_object(self):
        cached = self.__dict__.get("_content_object_cache", _UNSET)
        if cached is not _UNSET:
            return cached
        if self.content_type_id is None or self.object_id is None:
            return None
        model_class = self.content_type.model_class()
        if self.content_object_domain_id is not None:
            alias = self.content_object_domain.database_alias
            try:
                resolved = model_class.objects.using(alias).get(pk=self.object_id)
            except model_class.DoesNotExist:
                _logger.warning(
                    "content_object for %s (pk=%s) not found on alias '%s' "
                    "(content_type_id=%s, object_id=%s). The referenced object may have been "
                    "deleted, or Domain replication for this row's domain may be stale -- run "
                    "'pulpcore-manager sync-domains' to check.",
                    self._meta.label,
                    self.pk,
                    alias,
                    self.content_type_id,
                    self.object_id,
                )
                resolved = None
        else:
            try:
                resolved = model_class._base_manager.using(self._state.db or "default").get(
                    pk=self.object_id
                )
            except model_class.DoesNotExist:
                resolved = None
        self.__dict__["_content_object_cache"] = resolved
        return resolved

    @content_object.setter
    def content_object(self, value):
        self.__dict__["_content_object_cache"] = value
        if value is None:
            self.content_type = None
            self.object_id = None
            self.content_object_domain_id = None
            return
        gfk = type(self)._content_object
        self.content_type = ContentType.objects.db_manager("default").get_for_model(
            value, for_concrete_model=gfk.for_concrete_model
        )
        self.object_id = value.pk
        self.content_object_domain_id = _resolve_domain_id(value)


class GenericRelationModel(DomainResolvedGenericRelation, BaseModel):
    """Base model class for implementing Generic Relations.

    This class provides the required fields to implement generic relations. Instances of
    this class can only be related models with a primary key, such as those subclassing
    Pulp's base Model class.
    """

    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.UUIDField()
    _content_object = GenericForeignKey("content_type", "object_id", for_concrete_model=False)
    content_object_domain = models.ForeignKey(
        "core.Domain", null=True, on_delete=models.SET_NULL, related_name="+"
    )

    class Meta:
        abstract = True
