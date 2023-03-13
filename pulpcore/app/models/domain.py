from django.core.files.storage import get_storage_class, default_storage
from django.db import models
from django_lifecycle import hook, BEFORE_DELETE, BEFORE_UPDATE

from pulpcore.app.models import BaseModel, AutoAddObjPermsMixin

from .fields import EncryptedJSONField


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
        description (models.TextField): Optional description of domain
        storage_class (models.TextField): Required storage class for backend
        storage_settings (EncryptedJSONField): Settings needed to configure storage backend
        redirect_to_object_storage (models.BooleanField): Redirect to object storage in content app
        hide_guarded_distributions (models.BooleanField): Hide guarded distributions in content app
    """

    name = models.SlugField(null=False, unique=True)
    description = models.TextField(null=True)
    # Storage class is required, optional settings are validated by serializer
    storage_class = models.TextField(null=False)
    storage_settings = EncryptedJSONField(default=dict)
    # Pulp settings that are appropriate to be set on a "per domain" level
    redirect_to_object_storage = models.BooleanField(default=True)
    hide_guarded_distributions = models.BooleanField(default=False)

    def get_storage(self):
        """Returns this domain's instantiated storage class."""
        if self.name == "default":
            return default_storage
        storage_class = get_storage_class(self.storage_class)
        return storage_class(**self.storage_settings)

    @hook(BEFORE_DELETE, when="name", is_now="default")
    @hook(BEFORE_UPDATE, when="name", was="default")
    def prevent_default_deletion(self):
        raise models.ProtectedError("Default domain can not be updated/deleted.", [self])

    class Meta:
        permissions = [
            ("manage_roles_domain", "Can manage role assignments on domain"),
        ]
