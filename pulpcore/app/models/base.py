from django.db import models
from django.db.models import options

import uuid


class Model(models.Model):
    """Base model class for all Pulp models.

    Fields:
        _created (models.DateTimeField): Created timestamp UTC.
        _last_updated (models.DateTimeField): Last updated timestamp UTC.

    References:

        * https://docs.djangoproject.com/en/1.8/topics/db/models/#automatic-primary-key-fields

    """
    _id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    _created = models.DateTimeField(auto_now_add=True)
    _last_updated = models.DateTimeField(auto_now=True, null=True)

    class Meta:
        abstract = True

    def __str__(self):
        try:
            # if we have a name, use it
            return '<{}: {}>'.format(self._meta.object_name, self.name)
        except AttributeError:
            # if we don't, use the pk
            return '<{}: pk={}>'.format(self._meta.object_name, self.pk)

    def __repr__(self):
        return str(self)


class MasterModel(Model):
    """Base model for the "Master" model in a "Master-Detail" relationship.

    Provides methods for casting down to detail types, back up to the master type,
    as well as a model field for tracking the type.

    Attributes:

        TYPE (str): Default constant value saved into the ``_type``
            field of Model instances

    Fields:

        _type: The user-facing string identifying the detail type of this model

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
    # creating a Remote Detail class like PackageRemote, its _type value could be "package",
    # not "package_remote", since "package_remote" would be redundant in the context of
    # a remote Master model.
    TYPE = None

    # This field must have a value when models are saved, and defaults to the value of
    # the TYPE attribute on the Model being saved (seen above).
    _type = models.TextField(null=False, default=None)

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        # instances of "detail" models that subclass MasterModel are exposed
        # on instances of MasterModel by the string stored in that model's TYPE attr.
        # Storing this _type in a column on the MasterModel next to makes it trivial
        # to filter for specific detail model types across master's relations.
        # Prepend the TYPE defined on a detail model with a django app label.
        # If a plugin sets the type field themselves, it's used as-is.
        if not self._type:
            self._type = '{app_label}.{type}'.format(app_label=self._meta.app_label,
                                                     type=self.TYPE)
        return super().save(*args, **kwargs)

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
        """The "Master" model instance of this master-detail pair

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
            return '<{} (_type={}): {}>'.format(self._meta.object_name, cast.TYPE, cast.name)
        except AttributeError:
            return '<{} (_type={}): pk={}>'.format(self._meta.object_name, cast.TYPE, cast.pk)


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
