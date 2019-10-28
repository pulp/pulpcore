from gettext import gettext as _
from urllib.parse import urljoin

from django.core.validators import URLValidator
from drf_queryfields.mixins import QueryFieldsMixin
from rest_framework import serializers
from rest_framework_nested.relations import (
    NestedHyperlinkedIdentityField,
    NestedHyperlinkedRelatedField,
)

from pulpcore.app.models import Task
from pulpcore.app.util import get_view_name_for_model


def validate_unknown_fields(initial_data, defined_fields):
    """
    This will raise a `ValidationError` if a serializer is passed fields that are unknown.
    The `csrfmiddlewaretoken` field is silently ignored.
    """
    ignored_fields = {'csrfmiddlewaretoken'}
    unknown_fields = set(initial_data) - set(defined_fields) - ignored_fields
    if unknown_fields:
        unknown_fields = {field: _('Unexpected field') for field in unknown_fields}
        raise serializers.ValidationError(unknown_fields)


class ModelSerializer(QueryFieldsMixin, serializers.HyperlinkedModelSerializer):
    """Base serializer for use with :class:`pulpcore.app.models.Model`

    This ensures that all Serializers provide values for the 'pulp_href` field.

    The class provides a default for the ``ref_name`` attribute in the
    ModelSerializers's ``Meta`` class. This ensures that the OpenAPI definitions
    of plugins are namespaced properly.

    """

    # default is 'fields!' which doesn't work in the bindings for some langs
    exclude_arg_name = "exclude_fields"

    class Meta:
        fields = ('pulp_href', 'pulp_created')

    pulp_created = serializers.DateTimeField(
        help_text=_('Timestamp of creation.'),
        read_only=True
    )

    def _validate_relative_path(self, path):
        """
        Validate a relative path (eg from a url) to ensure it forms a valid url and does not begin
        or end with slashes nor contain spaces

        Args:
            path (str): A relative path to validate

        Returns:
            str: the validated path

        Raises:
            django.core.exceptions.ValidationError: if the relative path is invalid

        """
        # in order to use django's URLValidator we need to construct a full url
        base = "http://localhost"  # use a scheme/hostname we know are valid

        if ' ' in path:
            raise serializers.ValidationError(detail=_("Relative path cannot contain spaces."))

        validate = URLValidator()
        validate(urljoin(base, path))

        if path != path.strip("/"):
            raise serializers.ValidationError(detail=_("Relative path cannot begin or end with "
                                                       "slashes."))

        return path

    def validate(self, data):
        if hasattr(self, 'initial_data'):
            validate_unknown_fields(self.initial_data, self.fields)
        return data

    def __init_subclass__(cls, **kwargs):
        """Set default attributes in subclasses.

        Sets the default for the ``ref_name`` attribute for a ModelSerializers's
        ``Meta`` class.

        If the ``Meta.ref_name`` attribute is not yet defined, set it according
        to the best practice established within Pulp: ``<app label>.<model class
        name>``. ``app_label`` is used to create a per plugin namespace.

        Serializers in pulpcore (``app_label`` is 'core') will not be
        namespaced, i.e. ref_name is not set in this case.

        The ``ref_name`` default value is computed using ``Meta.model``. If that
        is not defined (because the class must be subclassed to be useful),
        `ref_name` is not set.

        """
        super().__init_subclass__(**kwargs)
        meta = cls.Meta
        try:
            if not hasattr(meta, "ref_name"):
                plugin_namespace = meta.model._meta.app_label
                if plugin_namespace != "core":
                    meta.ref_name = f"{plugin_namespace}.{meta.model.__name__}"
        except AttributeError:
            pass


class MatchingNullViewName(object):
    """Object that can be used as the default view name for detail fields

    This is needed to bypass a view name check done in DRF's to_internal_value method
    that checks that the view name for the incoming data matches the view name it expects
    for the object being represented. Since we don't know the view name for that object
    until it's been cast, and it doesn't get cast until get_object is called, and this
    check happens immediately before get_object is called, this check is probitive to our
    implementation. Setting the default view_name attr of a Detail related or identity
    field to an instance of this class should ensure the the view_name attribute of one
    of these related fields is equal to any view name it's compared to, bypassing DRF's
    view_name matching check.
    """

    def __eq__(self, other):
        return True


class _DetailFieldMixin:
    """Mixin class containing code common to DetailIdentityField and DetailRelatedField"""

    def __init__(self, view_name=None, **kwargs):
        if view_name is None:
            # set view name to prevent a DRF assertion that view_name is not None
            # Anything that accesses self.view_name after __init__
            # needs to have it set before being called. Unfortunately, a model instance
            # is required to derive this value, so we can't make a view_name property.
            view_name = MatchingNullViewName()
        super().__init__(view_name, **kwargs)

    def _view_name(self, obj):
        # this is probably memoizeable based on the model class if we want to get cachey
        try:
            obj = obj.cast()
        except AttributeError:
            # The normal message that comes up here is unhelpful, so do like other DRF
            # fails do and be a little more helpful in the exception message.
            msg = ('Expected a detail model instance, not {}. Do you need to add "many=True" to '
                   'this field definition in its serializer?').format(type(obj))
            raise ValueError(msg)
        return get_view_name_for_model(obj, 'detail')

    def get_url(self, obj, view_name, request, *args, **kwargs):
        # ignore the passed in view name and return the url to the cast unit, not the generic unit
        request = None
        view_name = self._view_name(obj)
        return super().get_url(obj, view_name, request, *args, **kwargs)


class IdentityField(serializers.HyperlinkedIdentityField):
    """IdentityField for use in the pulp_href field of non-Master/Detail Serializers.

    The get_url method is overriden so relative URLs are returned.
    """

    def get_url(self, obj, view_name, request, *args, **kwargs):
        # ignore the passed in view name and return the url to the cast unit, not the generic unit
        request = None
        return super().get_url(obj, view_name, request, *args, **kwargs)


class RelatedField(serializers.HyperlinkedRelatedField):
    """RelatedField when relating to non-Master/Detail models

    When using this field on a serializer, it will serialize the related resource as a relative URL.
    """

    def get_url(self, obj, view_name, request, *args, **kwargs):
        # ignore the passed in view name and return the url to the cast unit, not the generic unit
        request = None
        return super().get_url(obj, view_name, request, *args, **kwargs)


class DetailIdentityField(_DetailFieldMixin, serializers.HyperlinkedIdentityField):
    """IdentityField for use in the pulp_href field of Master/Detail Serializers

    When using this field on a Serializer, it will automatically cast objects to their Detail type
    base on the Serializer's Model before generating URLs for them.

    Subclasses must indicate the Master model they represent by declaring a queryset
    in their class body, usually <MasterModelImplementation>.objects.all().
    """


class DetailRelatedField(_DetailFieldMixin, serializers.HyperlinkedRelatedField):
    """RelatedField for use when relating to Master/Detail models

    When using this field on a Serializer, relate it to the Master model in a
    Master/Detail relationship, and it will automatically cast objects to their Detail type
    before generating URLs for them.

    Subclasses must indicate the Master model they represent by declaring a queryset
    in their class body, usually <MasterModelImplementation>.objects.all().
    """

    def get_object(self, *args, **kwargs):
        # return the cast object, not the generic contentunit
        return super().get_object(*args, **kwargs).cast()

    def use_pk_only_optimization(self):
        """
        If the lookup field is `pk`, DRF substitutes a PKOnlyObject as an optimization. This
        optimization breaks with Detail fields like this one which need access to their Meta
        class to get the relevant `view_name`.
        """
        return False


class NestedIdentityField(NestedHyperlinkedIdentityField):
    """NestedIdentityField for use with nested resources.

    When using this field in a serializer, it serializes the resource as a relative URL.
    """

    def get_url(self, obj, view_name, request, *args, **kwargs):
        # ignore the passed in view name and return the url to the cast unit, not the generic unit
        request = None
        return super().get_url(obj, view_name, request, *args, **kwargs)


class NestedRelatedField(NestedHyperlinkedRelatedField):
    """NestedRelatedField for use when relating to nested resources.

    When using this field in a serializer, it serializes the related resource as a relative URL.
    """

    def get_url(self, obj, view_name, request, *args, **kwargs):
        # ignore the passed in view name and return the url to the cast unit, not the generic unit
        request = None
        return super().get_url(obj, view_name, request, *args, **kwargs)


class AsyncOperationResponseSerializer(serializers.Serializer):
    """
    Serializer for asynchronous operations.
    """
    task = RelatedField(
        required=True,
        help_text=_('The href of the task.'),
        queryset=Task.objects,
        view_name='tasks-detail',
        allow_null=False
    )
