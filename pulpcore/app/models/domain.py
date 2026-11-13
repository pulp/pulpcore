from django.contrib.postgres.fields import HStoreField
from django.core.files.storage import default_storage
from django.db import models
from django_lifecycle import BEFORE_DELETE, BEFORE_UPDATE, hook

from pulpcore.app.models import AutoAddObjPermsMixin, BaseModel
from pulpcore.app.util import get_domain_pk
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

    @property
    def default_content_guard(self):
        """The content-guard automatically assigned to new distributions in this domain."""
        try:
            return self.default_content_guard_mapping.content_guard
        except DomainDefaultContentGuard.DoesNotExist:
            return None

    def set_default_content_guard(self, content_guard):
        """Set, replace, or clear (with `None`) this domain's default content-guard."""
        if content_guard is None:
            DomainDefaultContentGuard.objects.filter(pulp_domain=self).delete()
        else:
            DomainDefaultContentGuard.objects.update_or_create(
                pulp_domain=self, defaults={"content_guard": content_guard}
            )
        self._state.fields_cache.pop("default_content_guard_mapping", None)

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

    @hook(BEFORE_DELETE, when="name", is_not="default")
    def _cleanup_orphans_pre_delete(self):
        protected_content_set = self.content_set.exclude(version_memberships__isnull=True)
        if protected_content_set.exists():
            raise DomainProtectedError()
        self.content_set.filter(version_memberships__isnull=True).delete()
        for artifact in self.artifact_set.all().iterator():
            # Delete on by one to properly cleanup the storage.
            artifact.delete()

    class Meta:
        permissions = [
            ("manage_roles_domain", "Can manage role assignments on domain"),
        ]


class DomainDefaultContentGuard(BaseModel):
    """
    The default content-guard of a Domain.

    Kept out of the Domain table so the relation lives next to the content-guard it references.

    Relations:
        pulp_domain (models.OneToOneField): The domain this default applies to.
        content_guard (models.ForeignKey): The content-guard automatically assigned to new
            distributions created within the domain.
    """

    pulp_domain = models.OneToOneField(
        Domain,
        default=get_domain_pk,
        on_delete=models.CASCADE,
        related_name="default_content_guard_mapping",
    )
    content_guard = models.ForeignKey("ContentGuard", on_delete=models.CASCADE, related_name="+")
