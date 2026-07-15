"""
Container for models using generic relations provided by Django's ContentTypes framework.

References:
    https://docs.djangoproject.com/en/3.2/ref/contrib/contenttypes/#generic-relations
"""

import logging

from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models

from pulpcore.app.models.base import BaseModel

_logger = logging.getLogger(__name__)


#: Sentinel distinguishing "no in-memory value cached yet" from a legitimately cached `None`
#: (a model-level `UserRole`/`GroupRole` grant has no target at all).
_UNSET = object()


class DomainResolvedGenericRelation:
    """
    Mixin providing a cross-database-safe `content_object` for models with a
    `content_type`/`object_id` `GenericForeignKey` pair whose target may be a data-plane object
    living on a different database alias than the row holding the FK (KI-18, Critical).

    Every model in pulpcore/plugins that declares a `GenericForeignKey` (`CreatedResource`,
    `ExportedResource`, `UserRole`, `GroupRole` -- no plugin declares its own, confirmed by
    full-codebase audit) is itself a control-plane model, always on `default`, while its target
    may be any model at all, including a data-plane one that has since moved to a satellite.
    Django's stock `GenericForeignKey` has *two* cross-DB landmines for exactly this shape,
    both found empirically (real multi-Postgres integration testing), not just by reading the
    design doc's KI-18 writeup (which only covers the first):

    1. `__get__` resolves the target using `instance._state.db` -- the *FK-holding row's*
       database, not the target's -- and silently swallows `ObjectDoesNotExist`, returning
       `None` with no error at all. For a moved domain, `.content_object` would quietly start
       returning `None` for every affected row: no exception, no log line, just wrong data (a
       task's created-resources page silently empty, an incremental export silently missing a
       repository version).
    2. `__set__` resolves the `ContentType` row for the target via
       `ContentType.objects.db_manager(value._state.db).get_for_model(value)` -- i.e. against
       *the target's own alias's* `django_content_type` table, not `default`'s. `ContentType.pk`
       is an independent per-database auto-increment (each alias runs its own
       `create_contenttypes` during `migrate`, in whatever order that alias's installed apps
       happen to migrate in), so the same `app_label`/`model` pair can end up with a *different*
       pk on a satellite than on `default`. Since this row is itself control-plane and always
       lives on `default`, its stored `content_type_id` must always be `default`'s id for that
       model -- storing the target-alias's id means a later read (which resolves `content_type`
       against `default`, since ContentType is control-plane) silently decodes it as whatever
       *different* model happens to have that id on `default`. Reproduced in integration testing
       as a `CreatedResource` for a `Repository` resolving to an unrelated `Remote` instead.

    Locked fix for #1 (see `architecture/domain-db-offloading-design.md`, KI-18): denormalize a
    nullable `content_object_domain` FK onto the model, auto-populated by the `content_object`
    setter below from `content_object.pulp_domain_id` whenever a target is set -- no call site
    needs to set it explicitly, and it's set eagerly (not deferred to `save()`) specifically so
    that `bulk_create()` -- which never calls `save()` -- still populates it correctly; see
    `pulpcore.app.viewsets.base.NamedModelViewSet.add_role` for a real `bulk_create()` call
    site. The `content_object` property below then resolves the target via
    `.using(content_object_domain.database_alias)` when that field is set, and falls back to
    resolving on this row's own alias whenever there's no recorded cross-plane domain (no
    target at all -- e.g. a model-level `UserRole`/`GroupRole` grant -- or a control-plane
    target, which lives on the same alias as this row anyway). Either way, a target that can't
    be resolved (deleted, or -- for the cross-plane case -- possibly stale Domain replication)
    logs and returns `None`, exactly like Django's own `GenericForeignKey.__get__` and like
    every existing call site already expects; it does not raise.

    Fix for #2: the setter below never delegates to Django's `GenericForeignKey.__set__` (would
    reintroduce the bug) -- it sets `content_type`/`object_id` directly, always resolving
    `ContentType` via `ContentType.objects.db_manager("default")` regardless of which alias the
    target object itself came from.

    Both the getter and setter also avoid Django's `GenericForeignKey.__get__`/`is_cached()`
    entirely for in-memory caching (a plain `_UNSET`-sentinelled instance attribute is used
    instead): `__get__`'s cache-validation re-resolves the cached value's `ContentType` via
    `value._state.db` again on every access (the same #2 landmine), which would otherwise
    spuriously invalidate a just-set cross-plane value on every subsequent access within the
    same process, even before any DB round-trip.

    Including models must declare the real `GenericForeignKey` under the name
    `_content_object` (not `content_object` -- kept only so `for_concrete_model` and the
    content_type/object_id field names stay introspectable/documented in one place, not because
    its `__get__`/`__set__` are actually used) and a nullable `content_object_domain` FK to
    `core.Domain`. This mixin then makes `content_object` behave exactly like the original
    attribute at every one of pulpcore's/plugins' existing `content_object=` call sites --
    zero call-site changes required, including in code this audit didn't see (unaudited or
    future plugin code).
    """

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
            # Cross-plane target loaded fresh from the DB: resolve on the target's own alias,
            # not this (control-plane) row's alias -- this is the KI-18 fix.
            alias = self.content_object_domain.database_alias
            try:
                resolved = model_class.objects.using(alias).get(pk=self.object_id)
            except model_class.DoesNotExist:
                # Mirror Django's own GenericForeignKey.__get__ semantics (and the "no
                # cross-plane domain recorded" branch below): a missing target is far more
                # commonly a legitimately deleted object (e.g. a Task's created_resources
                # pointing at a since-destroyed Repository/Export) than stale Domain
                # replication, and every existing call site (RelatedResourceField,
                # CreatedResourcePrnField, delete_incomplete_resources, etc.) already treats
                # `content_object is None` as "gone, render/skip gracefully". Raising here
                # instead turned that everyday case into an unhandled 500
                # (see pulp task list rendering a Task whose created Export was deleted).
                # Still log so a genuinely-stale satellite is discoverable via
                # 'pulpcore-manager sync-domains', just without crashing the caller.
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
            # No cross-plane domain recorded: the target is itself control-plane, so it lives on
            # this (control-plane) row's own alias -- resolve there, mirroring normal Django GFK
            # behavior but without touching `_content_object`/`__get__` (see class docstring).
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
        # Always resolve against `default`, regardless of which alias `value` itself lives on --
        # see the class docstring's landmine #2. `db_manager` bypasses the router deliberately
        # (mirroring Django's own `get_content_type`), since ContentType is control-plane and
        # `.get_for_model()`'s cache is keyed per-alias already.
        self.content_type = ContentType.objects.db_manager("default").get_for_model(
            value, for_concrete_model=gfk.for_concrete_model
        )
        self.object_id = value.pk
        self.content_object_domain_id = getattr(value, "pulp_domain_id", None)


class GenericRelationModel(DomainResolvedGenericRelation, BaseModel):
    """Base model class for implementing Generic Relations.

    This class provides the required fields to implement generic relations. Instances of
    this class can only be related models with a primary key, such as those subclassing
    Pulp's base Model class.
    """

    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.UUIDField()
    _content_object = GenericForeignKey("content_type", "object_id", for_concrete_model=False)
    # KI-18: denormalized target domain, auto-populated by DomainResolvedGenericRelation's
    # `content_object` setter. Internal/operational only, like Domain.database_alias/moving --
    # not exposed via any serializer.
    content_object_domain = models.ForeignKey(
        "core.Domain", null=True, on_delete=models.SET_NULL, related_name="+"
    )

    class Meta:
        abstract = True
