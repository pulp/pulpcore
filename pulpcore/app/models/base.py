from gettext import gettext as _
import uuid

from django.contrib.contenttypes.fields import GenericRelation, GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.db.models import options
from django.db.models.base import ModelBase
from django_lifecycle import LifecycleModel

from pulpcore.app.loggers import deprecation_logger


def pulp_uuid():
    """
    Abstract wrapper for UUID generator.

    Allows the implementation to be swapped without triggering migrations.
    """
    return uuid.uuid4()


class Label(LifecycleModel):
    """
    Model for handling resource labels.

    Labels are key/value data that can be associated with any BaseModel.

    Fields:
        pulp_id (models.UUIDField): Primary key identifier
        object_id (models.UUIDField): Resource id
        key (models.CharField): Key of the label
        value (models.TextField): Value of the label

    Relations:
        content_object (GenericForeignKey): Associated resource
        content_type (models.ForeignKey): Content type of the resource
    """

    pulp_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.UUIDField()
    key = models.CharField(max_length=200, db_index=True)
    value = models.TextField(null=True, db_index=True)

    content_object = GenericForeignKey("content_type", "object_id", for_concrete_model=False)

    class Meta:
        unique_together = [["content_type", "object_id", "key"]]


class BaseModel(LifecycleModel):
    """
    Base model class for all Pulp models.

    This model inherits from `LifecycleModel` which allows all Pulp models to be used with
    `django-lifecycle`.

    Fields:
        pulp_created (models.DateTimeField): Created timestamp UTC.
        pulp_last_updated (models.DateTimeField): Last updated timestamp UTC.

    Relations:
        pulp_labels (GenericRelation): A list of key/value labels.

    References:

        * https://docs.djangoproject.com/en/1.8/topics/db/models/#automatic-primary-key-fields
        * https://rsinger86.github.io/django-lifecycle/

    """

    pulp_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    pulp_created = models.DateTimeField(auto_now_add=True)
    pulp_last_updated = models.DateTimeField(auto_now=True, null=True)
    pulp_labels = GenericRelation(Label)
    user_roles = GenericRelation("core.UserRole")
    group_roles = GenericRelation("core.GroupRole")

    class Meta:
        abstract = True

    def __init__(self, *args, **kwargs):
        if hasattr(self, "ACCESS_POLICY_VIEWSET_NAME"):
            deprecation_logger.warn(
                f"The model {self.__class__} defines the 'ACCESS_POLICY_VIEWSET_NAME' class "
                f"attribute which is no longer required and is discouraged to be set."
            )
        return super().__init__(*args, **kwargs)

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
        """Override __new__ to set the default_related_name."""
        if BaseModel not in bases and MasterModel not in bases:  # Only affects "Detail" models.
            meta = attrs.get("Meta")
            default_related_name = getattr(meta, "default_related_name", None)
            abstract = getattr(meta, "abstract", None)

            if not default_related_name and not abstract:
                raise Exception(
                    _("The 'default_related_name' option has not been set for {class_name}").format(
                        class_name=name
                    )
                )

        new_class = super().__new__(cls, name, bases, attrs, **kwargs)
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

    @classmethod
    def get_pulp_type(cls):
        """Get the "pulp_type" string associated with this MasterModel type."""
        return "{app_label}.{type}".format(app_label=cls._meta.app_label, type=cls.TYPE)

    def cast(self):
        """Return a "Detail" model instance of this master-detail pair.

        If this model is already an instance of its detail type, it will return itself.
        """
        # Go through our related objects, find the one that's a subclass of this model
        # on a OneToOneField, which identifies it as a potential detail relation.
        for rel in self._meta.related_objects:
            if rel.one_to_one and issubclass(rel.related_model, self._meta.model):
                # The name of this relation is the name of the attr on the model instance.
                # If that attr as a value, that means a row exists for this model in the
                # related detail table. Cast and return this value, recursively following
                # master/detail relationships down to the last table (the most detailed).
                try:
                    return getattr(self, rel.name).cast()
                except AttributeError:
                    continue
        else:
            # The for loop exited normally, there are no more detailed models than this
            # one in this instance's master/detail ancestry, so return here.
            return self

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
        cast = self.cast()
        if cast is self:
            return super().__str__()

        try:
            return "<{} (pulp_type={}): {}>".format(
                self._meta.object_name, cast.pulp_type, cast.name
            )
        except AttributeError:
            return "<{} (pulp_type={}): pk={}>".format(
                self._meta.object_name, cast.pulp_type, cast.pk
            )


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
