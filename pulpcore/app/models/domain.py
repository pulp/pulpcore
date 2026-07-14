from django.conf import settings
from django.contrib.postgres.fields import HStoreField
from django.core.exceptions import ValidationError
from django.core.files.storage import default_storage
from django.db import models
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
        database_alias (models.SlugField): The `settings.DATABASES` alias where this domain's
            data-plane objects (repositories, content, artifacts, etc.) reside. Defaults to
            "default" so existing single-database deployments are unaffected. This field is
            internal/operational only -- it is never exposed through the public API (see
            `DomainSerializer`) and is only ever changed by admin-run `pulpcore-manager`
            tooling (`move-domain`), never by end users.
        moving (models.BooleanField): Whether this domain is currently in the middle of being
            moved between database aliases by the `move-domain` command. While `True`, write
            operations for this domain are rejected and no new tasks are dispatched for it.
            Internal/operational only, same visibility rules as `database_alias`.
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
    # Internal/operational-only fields for domain-aware database routing. Never exposed via the
    # public API (intentionally excluded from DomainSerializer.Meta.fields) and only ever written
    # by admin-run `pulpcore-manager` CLI tooling (`move-domain`, `sync-domains`), never by
    # end users or any REST endpoint.
    database_alias = models.SlugField(
        default="default",
        help_text="DATABASES alias where this domain's data-plane objects reside.",
    )
    moving = models.BooleanField(
        default=False,
        help_text="True while this domain's data is being moved between database aliases.",
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
    @hook(BEFORE_UPDATE, when="database_alias", has_changed=True)
    def _validate_database_alias(self):
        """Ensure `database_alias` always refers to a real, configured DATABASES alias."""
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
        # This domain's data-plane objects may live on a satellite alias (KI-04): the reverse
        # FK managers below must be explicitly routed there, since the router's instance-hint
        # check only recognizes models with a `pulp_domain` attribute, which `self` (the Domain
        # itself) does not have.
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

    class Meta:
        permissions = [
            ("manage_roles_domain", "Can manage role assignments on domain"),
        ]
