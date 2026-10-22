from django.conf import settings
from django.contrib.postgres.fields import HStoreField
from django.core.exceptions import ValidationError
from django.core.files.storage import default_storage
from django.db import models
from django.db.models.deletion import PROTECT, get_candidate_relations_to_delete
from django_lifecycle import BEFORE_CREATE, BEFORE_DELETE, BEFORE_UPDATE, hook

from pulpcore.app.models import AutoAddObjPermsMixin, BaseModel
from pulpcore.exceptions import DomainProtectedError

from .fields import EncryptedJSONField

# Global used to store instantiated storage classes to speed up lookups across domains
storages = {}


class Domain(BaseModel, AutoAddObjPermsMixin):
    """
    A namespace-like object applied to most Pulp models to allow for multi-tenancy.

    Pulp models have a domain as a part of their uniqueness-constraint to provide isolation from
    other domains. Domains each have their own storage backend for storing and deduplicating
    Artifacts. Roles on a domain apply to all the objects in that domain.

    Domains are an opt-in feature so Pulp models need to have their domain relation set the default
    to the "default" Domain when not enabled. Also, plugins must add domain foreign-keys to their
    models to be compatible with domains.

    Fields:
        name (models.SlugField): Unique name of domain
        pulp_labels (HStoreField): Dictionary of string values
        description (models.TextField): Optional description of domain
        storage_class (models.TextField): Required storage class for backend
        storage_settings (EncryptedJSONField): Settings needed to configure storage backend
        redirect_to_object_storage (models.BooleanField): Redirect to object storage in content app
        hide_guarded_distributions (models.BooleanField): Hide guarded distributions in content app

    Relations:
        default_content_guard (models.ForeignKey): An optional content-guard automatically
            assigned to new distributions created within this domain.
    """

    name = models.SlugField(null=False, unique=True)
    pulp_labels = HStoreField(default=dict)
    description = models.TextField(null=True)
    # Storage class is required, optional settings are validated by serializer
    storage_class = models.TextField(null=False)
    storage_settings = EncryptedJSONField(default=dict)
    # Pulp settings that are appropriate to be set on a "per domain" level
    redirect_to_object_storage = models.BooleanField(default=True)
    hide_guarded_distributions = models.BooleanField(default=False)
    # related_name="+" suppresses the reverse accessor; use ContentGuard.pulp_domain to traverse.
    default_content_guard = models.ForeignKey(
        "ContentGuard", null=True, on_delete=models.SET_NULL, related_name="+"
    )
    database_alias = models.SlugField(
        default="default",
        help_text="DATABASES alias where this domain's data-plane objects reside.",
    )

    def get_storage(self):
        """Returns this domain's instantiated storage class."""
        if self.name == "default":
            return default_storage

        if date_storage_tuple := storages.get(self.pulp_id):
            last_updated, storage = date_storage_tuple
            if self.pulp_last_updated == last_updated:
                return storage

        from pulpcore.app.serializers import DomainSerializer

        storage = DomainSerializer(instance=self).create_storage()
        storages[self.pulp_id] = (self.pulp_last_updated, storage)
        return storage

    @hook(BEFORE_DELETE, when="name", is_now="default")
    @hook(BEFORE_UPDATE, when="name", was="default")
    def prevent_default_deletion(self):
        raise models.ProtectedError("Default domain can not be updated/deleted.", [self])

    @hook(BEFORE_CREATE)
    @hook(BEFORE_UPDATE, when="default_content_guard_id", has_changed=True)
    def _replicate_default_content_guard(self):
        # default_content_guard is a real FK, and Domain rows always live in 'default' (it's
        # control-plane -- see db_router.CONTROL_PLANE_LABELS), so the referenced ContentGuard
        # needs a local row in 'default' too, or this FK violates the moment this Domain row is
        # written. self.default_content_guard is expected to already be cached on this instance
        # (assigned as an object, not just a bare _id, by whatever creates/updates this Domain) --
        # fetching it fresh here would resolve via ambient routing, not necessarily the alias it
        # actually lives on.
        if self.default_content_guard_id is None:
            return
        from pulpcore.app.db_router import is_multi_db_routing_active

        if not is_multi_db_routing_active():
            return
        from pulpcore.app.content_guard_sync import replicate_content_guard_to_default

        replicate_content_guard_to_default(self.default_content_guard)

    @hook(BEFORE_CREATE)
    @hook(BEFORE_UPDATE, when="database_alias", has_changed=True)
    def _validate_database_alias(self):
        if self.database_alias not in settings.DATABASES:
            raise ValidationError(
                {
                    "database_alias": (
                        f"'{self.database_alias}' is not a configured DATABASES alias."
                    )
                }
            )

    @hook(BEFORE_DELETE, when="name", is_not="default")
    def _cleanup_orphans_pre_delete(self):
        protected_content_set = self.content_set.using(self.database_alias).exclude(
            version_memberships__isnull=True
        )
        if protected_content_set.exists():
            raise DomainProtectedError()
        self.content_set.using(self.database_alias).filter(
            version_memberships__isnull=True
        ).delete()
        for artifact in self.artifact_set.using(self.database_alias).all().iterator():
            # Delete on by one to properly cleanup the storage.
            artifact.delete()

        # Domain always lives in 'default' (it's control-plane), so Django's own PROTECT check
        # for this delete runs against 'default' and can't see anything living on
        # self.database_alias instead -- e.g. a Repository on a satellite alias. Without this,
        # the domain would be deletable on 'default' while repositories (or other PROTECT-related
        # data-plane rows) referencing it still exist on the satellite. Re-check every PROTECT
        # relation Django would otherwise check, pointed at the domain's own alias instead.
        # Existence-only: a full django.db.models.deletion.Collector walk constructs real model
        # instances, which trips over MasterModel's pulp_type lazy-reload for a deferred field
        # loaded from a non-ambient alias.
        for related in get_candidate_relations_to_delete(self._meta):
            if related.field.remote_field.on_delete is not PROTECT:
                continue
            related_model = related.related_model
            if (
                related_model.objects.using(self.database_alias)
                .filter(**{related.field.name: self})
                .exists()
            ):
                raise DomainProtectedError()

    class Meta:
        permissions = [
            ("manage_roles_domain", "Can manage role assignments on domain"),
        ]
