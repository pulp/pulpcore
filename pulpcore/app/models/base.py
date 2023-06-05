from gettext import gettext as _

from django.contrib.contenttypes.fields import GenericRelation
from django.db import models
from django.db.models import options
from django.db.models.base import ModelBase
from django_lifecycle import LifecycleModel
from functools import lru_cache
from uuid6 import uuid7


def pulp_uuid():
    """Abstract wrapper for UUID generator.

    Allows the implementation to be swapped without triggering migrations.
    """
    return uuid7()


class BaseModel(LifecycleModel):
    """
    Base model class for all Pulp models.

    This model inherits from `LifecycleModel` which allows all Pulp models to be used with
    `django-lifecycle`.

    Fields:
        pulp_created (models.DateTimeField): Created timestamp UTC.
        pulp_last_updated (models.DateTimeField): Last updated timestamp UTC.

    Relations:
        user_roles (GenericRelation): List of user role associations with this object.
        group_roles (GenericRelation): List of group role associations with this object.

    References:

        * https://docs.djangoproject.com/en/3.2/topics/db/models/#automatic-primary-key-fields
        * https://rsinger86.github.io/django-lifecycle/

    """

    pulp_id = models.UUIDField(primary_key=True, default=pulp_uuid, editable=False)
    pulp_created = models.DateTimeField(auto_now_add=True)
    pulp_last_updated = models.DateTimeField(auto_now=True, null=True)
    user_roles = GenericRelation("core.UserRole")
    group_roles = GenericRelation("core.GroupRole")

    class Meta:
        abstract = True

    @classmethod
    @lru_cache
    def get_field_names(cls):
        return [f.name for f in cls._meta.fields]

    def __str__(self):
        try:
            # if we have a name, use it
            return "<{}: {}>".format(self._meta.object_name, self.name)
        except AttributeError:
            # if we don't, use the pk
            return "<{}: pk={}>".format(self._meta.object_name, self.pk)

    def __repr__(self):
        return str(self)


class MasterModelMeta(ModelBase):
    def __new__(cls, name, bases, attrs, **kwargs):
        if BaseModel in bases:
            # This is MasterModel. Do nothing!
            return super().__new__(cls, name, bases, attrs, **kwargs)

        meta = attrs.get("Meta")
        abstract = getattr(meta, "abstract", None)
        if abstract:
            # This is an abstract subclass. Do nothing!
            return super().__new__(cls, name, bases, attrs, **kwargs)

        if MasterModel in bases:
            # This is a "Master" model. Initialize model map.
            attrs["_pulp_model_map"] = {}
        else:
            # This is a "Detail" model. This is a sanity check only.
            default_related_name = getattr(meta, "default_related_name", None)

            if not default_related_name:
                raise Exception(
                    _("The 'default_related_name' option has not been set for {class_name}").format(
                        class_name=name
                    )
                )

        new_class = super().__new__(cls, name, bases, attrs, **kwargs)
        # Register with model map.
        new_class._pulp_model_map[new_class.get_pulp_type()] = new_class
        return new_class


class MasterModel(BaseModel, metaclass=MasterModelMeta):
    """
    Base model for the "Master" model in a "Master-Detail" relationship.

    Provides methods for casting down to detail types, back up to the master type,
    as well as a model field for tracking the type.

    Attributes:

        TYPE (str): Default constant value saved into the ``pulp_type``
            field of Model instances

    Fields:

        pulp_type: The user-facing string identifying the detail type of this model

    Warning:
        Subclasses of this class rely on there being no other parent/child Model
        relationships than the Master/Detail relationship. All subclasses must use
        only abstract Model base classes for MasterModel to behave properly.
        Specifically, OneToOneField relationships must not be used in any MasterModel
        subclass.

    """

    # TYPE is the user-facing string that describes this type. It is used to construct API
    # endpoints for Detail models, and will be seen in the URLs generated for those Detail models.
    # It can also be used for filtering across a relation where a model is related to a Master
    # model. Set this to something reasonable in Master and Detail model classes, e.g. when
    # create a master model, like "Remote", its TYPE value could be "remote". Then, when
    # creating a Remote Detail class like PackageRemote, its pulp_type value could be "package",
    # not "package_remote", since "package_remote" would be redundant in the context of
    # a remote Master model.
    TYPE = None

    # This field must have a value when models are saved, and defaults to the value of
    # the TYPE attribute on the Model being saved (seen above).
    pulp_type = models.TextField(null=False, default=None, db_index=True)

    class Meta:
        abstract = True

    @classmethod
    def get_pulp_type(cls):
        """Get the "pulp_type" string associated with this MasterModel type."""
        return "{app_label}.{type}".format(app_label=cls._meta.app_label, type=cls.TYPE)

    @classmethod
    def get_model_for_pulp_type(cls, pulp_type):
        return cls._pulp_model_map[pulp_type]

    def save(self, *args, **kwargs):
        # instances of "detail" models that subclass MasterModel are exposed
        # on instances of MasterModel by the string stored in that model's TYPE attr.
        # Storing this pulp_type in a column on the MasterModel next to makes it trivial
        # to filter for specific detail model types across master's relations.
        # Prepend the TYPE defined on a detail model with a django app label.
        # If a plugin sets the type field themselves, it's used as-is.
        if not self.pulp_type:
            self.pulp_type = self.get_pulp_type()
        return super().save(*args, **kwargs)

    def cast(self):
        """Return the "Detail" model instance of this master-detail object.

        If this is already an instance of its detail type, it will return itself.
        """
        if self.pulp_type == self.get_pulp_type():
            return self
        result = self._pulp_model_map[self.pulp_type].objects.get(pk=self.pk)
        # Keep all the prefetched data around.
        result._state.fields_cache.update(self._state.fields_cache)
        return result

    async def acast(self):
        """Return the "Detail" model instance of this master-detail object (async).

        If this is already an instance of its detail type, it will return itself.
        """
        if self.pulp_type == self.get_pulp_type():
            return self
        result = await self._pulp_model_map[self.pulp_type].objects.aget(pk=self.pk)
        # Keep all the prefetched data around.
        result._state.fields_cache.update(self._state.fields_cache)
        return result

    @property
    def master(self):
        """
        The "Master" model instance of this master-detail pair

        If this is already the master model instance, it will return itself.
        """
        if self._meta.master_model:
            return self._meta.master_model(pk=self.pk)
        else:
            return self

    def __str__(self):
        # similar to Model's __str__, but type-aware
        return "<{} (pulp_type={}): pk={}>".format(self._meta.object_name, self.pulp_type, self.pk)


# Add properties to model _meta info to support master/detail models
# If this property is not None on a Model, then that Model is a Detail Model.
# Doing this in a non-monkeypatch way would mean a lot of effort to achieve the same result
# (e.g. custom model metaclass, custom Options implementation, etc). These could be classmethods
# on Model classes, but it's easy enough to use the model's _meta namespace to do this, since
# that's where other methods like this exist in Django.
def master_model(options):
    """
    The Master model class of this Model's Master/Detail relationship.

    Accessible at ``<model_class>._meta.master_model``, the Master model class in a Master/Detail
    relationship is the most generic non-abstract Model in this model's multiple-table chain
    of inheritance.

    If this model is not a detail model, None will be returned.
    """
    # If this isn't even a MasterModel descendant, don't bother.
    if not issubclass(options.model, MasterModel):
        return None
    try:
        # The last item in this list is the oldest ancestor. Since the MasterModel usage
        # is to declare your master by subclassing MasterModel, and MasterModel is abstract,
        # the oldest ancestor model is the Master Model.
        return options.get_parent_list()[-1]
    except IndexError:
        # Also None if this model is itself the master.
        return None


options.Options.master_model = property(master_model)
