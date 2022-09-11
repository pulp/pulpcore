from gettext import gettext as _
from logging import getLogger
import functools
import re
import traceback
from typing import List, TypedDict
from urllib.parse import urljoin

from django.conf import settings
from django.core.validators import URLValidator
from django.core.exceptions import ObjectDoesNotExist
from django.db import IntegrityError, transaction
from django.db.models import Model
from drf_queryfields.mixins import QueryFieldsMixin
from rest_framework import serializers
from rest_framework.fields import get_attribute
from rest_framework.validators import UniqueValidator
from rest_framework_nested.relations import (
    NestedHyperlinkedIdentityField,
    NestedHyperlinkedRelatedField,
)

from pulpcore.app.models import Label, Task, TaskGroup
from pulpcore.app.util import (
    get_view_name_for_model,
    get_viewset_for_model,
    get_request_without_query_params,
    get_domain,
)


log = getLogger(__name__)


# Field mixins


def _reverse(reverse, request, obj):
    """Include domain-path in reverse call if DOMAIN_ENABLED."""

    if settings.DOMAIN_ENABLED:

        @functools.wraps(reverse)
        def _patched_reverse(viewname, args=None, kwargs=None, **extra):
            kwargs = kwargs or {}
            domain_name = obj.pulp_domain.name if hasattr(obj, "pulp_domain") else "default"
            kwargs["pulp_domain"] = domain_name
            return reverse(viewname, args=args, kwargs=kwargs, **extra)

        return _patched_reverse

    return reverse


class HrefFieldMixin:
    """A mixin to configure related fields to generate relative hrefs."""

    def get_url(self, obj, view_name, request, *args, **kwargs):
        # Removes the request from the arguments to display relative hrefs.
        self.reverse = _reverse(self.reverse, request, obj)
        return super().get_url(obj, view_name, None, *args, **kwargs)


class _MatchingRegexViewName(object):
    """This is a helper class to help defining object matching rules for master-detail.

    If you can be specific, please specify the `view_name`, but if you cannot, this allows
    you to specify a regular expression like .e.g. `r"repositories(-.*/.*)?-detail"` to
    identify whether the provided resources view name belongs to any repository type.
    """

    __slots__ = ("pattern",)

    def __init__(self, pattern):
        self.pattern = pattern

    def __repr__(self):
        return f'{self.__class__.__name__}(r"{self.pattern}")'

    def __eq__(self, other):
        return re.fullmatch(self.pattern, other) is not None


class _DetailFieldMixin(HrefFieldMixin):
    """Mixin class containing code common to DetailIdentityField and DetailRelatedField"""

    def __init__(self, view_name=None, view_name_pattern=None, **kwargs):
        if view_name is None:
            # set view name to prevent a DRF assertion that view_name is not None
            # Anything that accesses self.view_name after __init__
            # needs to have it set before being called. Unfortunately, a model instance
            # is required to derive this value, so we can't make a view_name property.
            if view_name_pattern:
                view_name = _MatchingRegexViewName(view_name_pattern)
            else:
                log.warn(
                    _(
                        "Please provide either 'view_name' or 'view_name_pattern' for {} on {}."
                    ).format(self.__class__.__name__, traceback.extract_stack()[-4][2])
                )
                view_name = _MatchingRegexViewName(r".*")
        super().__init__(view_name, **kwargs)

    def _view_name(self, obj):
        # this is probably memoizeable based on the model class if we want to get cachey
        try:
            obj = obj.cast()
        except AttributeError:
            # The normal message that comes up here is unhelpful, so do like other DRF
            # fails do and be a little more helpful in the exception message.
            msg = (
                'Expected a detail model instance, not {}. Do you need to add "many=True" to '
                "this field definition in its serializer?"
            ).format(type(obj))
            raise ValueError(msg)
        return get_view_name_for_model(obj, "detail")

    def get_url(self, obj, view_name, request, *args, **kwargs):
        # ignore the passed in view name and return the url to the cast unit, not the generic unit
        view_name = self._view_name(obj)
        return super().get_url(obj, view_name, request, *args, **kwargs)


# Fields


class IdentityField(
    HrefFieldMixin,
    serializers.HyperlinkedIdentityField,
):
    """IdentityField for use in the pulp_href field of non-Master/Detail Serializers.

    When using this field on a serializer, it will serialize the related resource as a relative URL.
    """


class RelatedField(
    HrefFieldMixin,
    serializers.HyperlinkedRelatedField,
):
    """RelatedField when relating to non-Master/Detail models

    When using this field on a serializer, it will serialize the related resource as a relative URL.
    """


class RelatedResourceField(RelatedField):
    """RelatedResourceField when relating a Resource object models.

    This field should be used to relate a list of non-homogeneous resources. e.g.:
    CreatedResource and ExportedResource models that store relationships to arbitrary
    resources.

    Specific implementation requires the model to be defined in the Meta:.
    """

    def to_representation(self, data):
        # If the content object was deleted
        if data.content_object is None:
            return None
        try:
            if not data.content_object.complete:
                return None
        except AttributeError:
            pass

        # query parameters can be ignored because we are looking just for 'pulp_href'; still,
        # we need to use the request object due to contextual references required by some
        # serializers
        request = get_request_without_query_params(self.context)

        viewset = get_viewset_for_model(data.content_object)
        serializer = viewset.serializer_class(data.content_object, context={"request": request})
        return serializer.data.get("pulp_href")


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


class NestedIdentityField(HrefFieldMixin, NestedHyperlinkedIdentityField):
    """NestedIdentityField for use with nested resources.

    When using this field in a serializer, it serializes the resource as a relative URL.
    """


class NestedRelatedField(
    HrefFieldMixin,
    NestedHyperlinkedRelatedField,
):
    """NestedRelatedField for use when relating to nested resources.

    When using this field in a serializer, it serializes the related resource as a relative URL.
    """


# Serializer mixins


def validate_unknown_fields(initial_data, defined_fields):
    """
    This will raise a `ValidationError` if a serializer is passed fields that are unknown.
    The `csrfmiddlewaretoken` field is silently ignored.
    """
    ignored_fields = {"csrfmiddlewaretoken"}
    unknown_fields = set(initial_data) - set(defined_fields) - ignored_fields
    if unknown_fields:
        unknown_fields = {field: _("Unexpected field") for field in unknown_fields}
        raise serializers.ValidationError(unknown_fields)


class ValidateFieldsMixin:
    """A mixin for validating unknown serializers' fields."""

    CHECK_SAME_DOMAIN = True

    def validate(self, data):
        if hasattr(self, "initial_data"):
            validate_unknown_fields(self.initial_data, self.fields)

        self.check_cross_domains(data)

        data = super().validate(data)
        return data

    def check_cross_domains(self, data):
        if not self.CHECK_SAME_DOMAIN:
            return
        current_domain = get_domain()
        for lvalue in data.values():
            if isinstance(lvalue, dict):
                self.check_cross_domains(lvalue)
                continue
            elif not isinstance(lvalue, list):
                lvalue = [lvalue]
            for value in lvalue:
                if isinstance(value, Model) and (
                    domain_id := getattr(value, "pulp_domain_id", None)
                ):
                    if current_domain.pulp_id != domain_id:
                        raise serializers.ValidationError(
                            _("Objects must all be apart of the {} domain.").format(
                                current_domain.name
                            )
                        )


class HiddenFieldsMixin(serializers.Serializer):
    """
    Adds a list field of hidden (write only) fields and whether their values are set
    so clients can tell if they are overwriting an existing value.
    For example this could be any sensitive information such as a password, name or token.
    The list contains dictionaries with keys `name` and `is_set`.
    """

    hidden_fields = serializers.SerializerMethodField(
        help_text=_("List of hidden (write only) fields")
    )

    def get_hidden_fields(
        self, obj
    ) -> List[TypedDict("hidden_fields", {"name": str, "is_set": bool})]:
        hidden_fields = []

        # returns false if field is "" or None
        def _is_set(field_name):
            field_value = get_attribute(obj, [field_name])
            return field_value != "" and field_value is not None

        fields = self.get_fields()
        for field_name in fields:
            if fields[field_name].write_only:
                hidden_fields.append({"name": field_name, "is_set": _is_set(field_name)})

        return hidden_fields


class GetOrCreateSerializerMixin:
    """A mixin that provides a get_or_create with validation in the serializer"""

    @classmethod
    def get_or_create(cls, natural_key, default_values=None):
        try:
            result = cls.Meta.model.objects.get(**natural_key)
        except ObjectDoesNotExist:
            data = {}
            if default_values:
                data.update(default_values)
            data.update(natural_key)
            serializer = cls(data=data)
            try:
                serializer.is_valid(raise_exception=True)
                result = serializer.create(serializer.validated_data)
            except (IntegrityError, serializers.ValidationError):
                # recover from a race condition, where another thread just created the object
                result = cls.Meta.model.objects.get(**natural_key)
        return result


class DomainUniqueValidator(UniqueValidator):
    """Special UniqueValidator for Models with pulp_domain relations."""

    def filter_queryset(self, value, queryset, field_name):
        """Filter by domain first to limit unique check to that domain."""
        queryset = queryset.filter(pulp_domain=get_domain())
        return super().filter_queryset(value, queryset, field_name)


# Serializers


class ModelSerializer(
    ValidateFieldsMixin, QueryFieldsMixin, serializers.HyperlinkedModelSerializer
):
    """Base serializer for use with :class:`pulpcore.app.models.Model`

    This ensures that all Serializers provide values for the 'pulp_href` field.

    The class provides a default for the ``ref_name`` attribute in the
    ModelSerializers's ``Meta`` class. This ensures that the OpenAPI definitions
    of plugins are namespaced properly.

    """

    # default is 'fields!' which doesn't work in the bindings for some langs
    exclude_arg_name = "exclude_fields"

    class Meta:
        fields = ("pulp_href", "pulp_created")

    pulp_created = serializers.DateTimeField(help_text=_("Timestamp of creation."), read_only=True)

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

        if " " in path:
            raise serializers.ValidationError(detail=_("Relative path cannot contain spaces."))

        validate = URLValidator()
        validate(urljoin(base, path))

        if path != path.strip("/"):
            raise serializers.ValidationError(
                detail=_("Relative path cannot begin or end with slashes.")
            )

        return path

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

    def _update_labels(self, instance, labels):
        """
        Update the labels for a Model instance.

        Args:
            instance (pulpcore.app.models.BaseModel): instance with labels to update
            labels (list): labels to set for the instance
        """
        instance.pulp_labels.exclude(key__in=labels.keys()).delete()

        for key, value in labels.items():
            label = instance.pulp_labels.filter(key=key).first()
            try:
                label = instance.pulp_labels.get(key=key)
                if label.value != value:
                    instance.pulp_labels.filter(key=key).update(value=value)
            except Label.DoesNotExist:
                instance.pulp_labels.create(key=key, value=value)

    def create(self, validated_data):
        """
        Created the resource from validated_data.

        Args:
            validated_data (dict): Validated data to create instance

        Returns:
            instance: The created of resource
        """
        # Circular import (But this is intended to be removed in 3.25 anyway).
        from pulpcore.app.serializers import LabelsField

        if not isinstance(self.fields.get("pulp_labels"), LabelsField):
            return super().create(validated_data)
        labels = validated_data.pop("pulp_labels", {})
        with transaction.atomic():
            instance = super().create(validated_data)
            self._update_labels(instance, labels)
        return instance

    def update(self, instance, validated_data):
        """
        Update the resource from validated_data.

        Args:
            validated_data (dict): Validated data to update instance

        Returns:
            instance: The updated instance of resource
        """
        # Circular import (But this is intended to be removed in 3.25 anyway).
        from pulpcore.app.serializers import LabelsField

        if not isinstance(self.fields.get("pulp_labels"), LabelsField):
            return super().update(instance, validated_data)
        labels = validated_data.pop("pulp_labels", None)
        with transaction.atomic():
            instance = super().update(instance, validated_data)
            if labels is not None:
                self._update_labels(instance, labels)
        return instance


class AsyncOperationResponseSerializer(serializers.Serializer):
    """
    Serializer for asynchronous operations.
    """

    task = RelatedField(
        required=True,
        help_text=_("The href of the task."),
        queryset=Task.objects,
        view_name="tasks-detail",
        allow_null=False,
    )


class TaskGroupOperationResponseSerializer(serializers.Serializer):
    """
    Serializer for asynchronous operations that return a task group.
    """

    task_group = RelatedField(
        required=True,
        help_text=_("The href of the task group."),
        queryset=TaskGroup.objects,
        view_name="task-groups-detail",
        allow_null=False,
    )
