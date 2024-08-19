from gettext import gettext as _

import pyparsing as pp

from functools import lru_cache, partial
from urllib.parse import urlparse
from uuid import UUID
from django import forms
from django.db import models
from django.forms.utils import ErrorList
from django.urls import Resolver404, resolve
from django_filters.constants import EMPTY_VALUES
from django_filters.rest_framework import DjangoFilterBackend, filterset, filters, BaseInFilter
from django.core.exceptions import FieldDoesNotExist
from rest_framework import serializers

from drf_spectacular.types import OpenApiTypes
from drf_spectacular.plumbing import build_basic_type
from drf_spectacular.contrib.django_filters import DjangoFilterExtension

from pulpcore.app.util import extract_pk

EMPTY_VALUES = (*EMPTY_VALUES, "null")


class StableOrderingFilter(filters.OrderingFilter):
    """
    Ordering filter with a stabilized order by either creation date, if available or primary key.
    """

    def filter(self, qs, value):
        try:
            field = qs.model._meta.get_field("pulp_created")
        except FieldDoesNotExist:
            field = qs.model._meta.pk

        ordering = [self.get_ordering_value(param) for param in value or []]
        ordering.append("-" + field.name)
        return qs.order_by(*ordering)


class HyperlinkRelatedFilter(filters.Filter):
    """
    Enables a user to filter by a foreign key using that FK's href.

    Foreign key filter can be specified to an object type by specifying the base URI of that type.
    e.g. Filter by file remotes: ?remote=/pulp/api/v3/remotes/file/file/

    Can also filter for foreign key to be unset by setting ``allow_null`` to True. Query parameter
    will then accept "null" or "" for filtering.
    e.g. Filter for no remote: ?remote="null"
    """

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("help_text", _("Foreign Key referenced by HREF"))
        self.allow_null = kwargs.pop("allow_null", False)
        super().__init__(*args, **kwargs)

    def _resolve_uri(self, uri):
        try:
            return resolve(urlparse(uri).path)
        except Resolver404:
            raise serializers.ValidationError(
                detail=_("URI couldn't be resolved: {uri}".format(uri=uri))
            )

    def _check_subclass(self, qs, uri, match):
        fields_model = getattr(qs.model, self.field_name).get_queryset().model
        lookups_model = match.func.cls.queryset.model
        if not issubclass(lookups_model, fields_model):
            raise serializers.ValidationError(
                detail=_("URI is not a valid href for {field_name} model: {uri}").format(
                    field_name=self.field_name, uri=uri
                )
            )

    def _check_valid_uuid(self, uuid):
        if not uuid:
            return True
        try:
            UUID(uuid, version=4)
        except ValueError:
            raise serializers.ValidationError(detail=_("UUID invalid: {uuid}").format(uuid=uuid))

    def _validations(self, *args, **kwargs):
        self._check_valid_uuid(kwargs["match"].kwargs.get("pk"))
        self._check_subclass(*args, **kwargs)

    def filter(self, qs, value):
        """
        Args:
            qs (django.db.models.query.QuerySet): The Queryset to filter
            value (string or list of strings): href containing pk for the foreign key instance

        Returns:
            django.db.models.query.QuerySet: Queryset filtered by the foreign key pk
        """

        if value is None:
            # value was not supplied by the user
            return qs

        if not self.allow_null and not value:
            raise serializers.ValidationError(
                detail=_("No value supplied for {name} filter.").format(name=self.field_name)
            )

        if self.allow_null and value in EMPTY_VALUES:
            return qs.filter(**{f"{self.field_name}__isnull": True})

        if self.lookup_expr == "in":
            matches = {uri: self._resolve_uri(uri) for uri in value}
            [self._validations(qs, uri=uri, match=matches[uri]) for uri in matches]
            value = [pk if (pk := matches[match].kwargs.get("pk")) else match for match in matches]
        else:
            match = self._resolve_uri(value)
            self._validations(qs, uri=value, match=match)
            if pk := match.kwargs.get("pk"):
                value = pk
            else:
                return qs.filter(**{f"{self.field_name}__in": match.func.cls.queryset})

        return super().filter(qs, value)


class IdInFilter(BaseInFilter, filters.UUIDFilter):
    def filter(self, qs, value):
        if value is None:
            return qs
        return qs.filter(pk__in=value)


class HREFInFilter(BaseInFilter, filters.CharFilter):
    def filter(self, qs, value):
        if value is None:
            return qs

        pks = [extract_pk(href) for href in value]
        return qs.filter(pk__in=pks)


class PulpTypeFilter(filters.ChoiceFilter):
    """Special pulp_type filter only added to generic list endpoints."""

    def __init__(self, *args, **kwargs):
        self.model = kwargs.pop("model", None)
        if self.model:
            kwargs["choices"] = self.pulp_type_choices(self.model)
        kwargs.setdefault("help_text", "")
        super().__init__(*args, **kwargs)

    @staticmethod
    @lru_cache
    def pulp_type_choices(model):
        """Extract the pulp_type choices from model."""
        choices = []
        for rel in model._meta.related_objects:
            if rel.one_to_one and issubclass(rel.related_model, model):
                pulp_type = rel.related_model.get_pulp_type()
                choices.append((pulp_type, pulp_type))
        return choices


class PulpTypeInFilter(BaseInFilter, PulpTypeFilter):
    """Special pulp_type filter only added to generic list endpoints."""


class ExpressionFilterField(forms.CharField):
    class _FilterAction:
        def __init__(self, filterset, tokens):
            key = tokens[0].key
            value = tokens[0].value
            self.filter = filterset.filters.get(key)
            if self.filter is None:
                raise forms.ValidationError(_("Filter '{key}' does not exist.").format(key=key))
            if isinstance(self.filter, ExpressionFilter):
                raise forms.ValidationError(
                    _("You cannot use '{key}' in complex filtering.").format(key=key)
                )
            if isinstance(self.filter, filters.OrderingFilter):
                raise forms.ValidationError(
                    _("An ordering filter cannot be used in complex filtering.")
                )
            form = filterset.form.__class__({key: value})
            if not form.is_valid():
                raise forms.ValidationError(form.errors.as_json())
            self.value = form.cleaned_data[key]
            self.complexity = 1

        def evaluate(self, qs):
            return self.filter.filter(qs, self.value)

    class _NotAction:
        def __init__(self, tokens):
            self.expr = tokens[0][0]
            self.complexity = self.expr.complexity + 1

        def evaluate(self, qs):
            return qs.difference(self.expr.evaluate(qs))

    class _AndAction:
        def __init__(self, tokens):
            self.exprs = tokens[0]
            self.complexity = sum((expr.complexity for expr in self.exprs)) + 1

        def evaluate(self, qs):
            return (
                self.exprs[0]
                .evaluate(qs)
                .intersection(*[expr.evaluate(qs) for expr in self.exprs[1:]])
            )

    class _OrAction:
        def __init__(self, tokens):
            self.exprs = tokens[0]
            self.complexity = sum((expr.complexity for expr in self.exprs)) + 1

        def evaluate(self, qs):
            return self.exprs[0].evaluate(qs).union(*[expr.evaluate(qs) for expr in self.exprs[1:]])

    def __init__(self, *args, **kwargs):
        self.filterset = kwargs.pop("filter").parent
        super().__init__(*args, **kwargs)

    def clean(self, value):
        value = super().clean(value)
        if value not in EMPTY_VALUES:
            slug = pp.Word(pp.alphas, pp.alphanums + "_")
            word = pp.Word(pp.alphanums + pp.alphas8bit + ".,_-*")
            rhs = word | pp.quoted_string.set_parse_action(pp.remove_quotes)
            group = pp.Group(
                slug.set_results_name("key")
                + pp.Suppress(pp.Literal("="))
                + rhs.set_results_name("value")
            ).set_parse_action(partial(self._FilterAction, self.filterset))

            expr = pp.infix_notation(
                group,
                [
                    (pp.Suppress(pp.Keyword("NOT")), 1, pp.opAssoc.RIGHT, self._NotAction),
                    (pp.Suppress(pp.Keyword("AND")), 2, pp.opAssoc.LEFT, self._AndAction),
                    (pp.Suppress(pp.Keyword("OR")), 2, pp.opAssoc.LEFT, self._OrAction),
                ],
            )
            try:
                result = expr.parse_string(value, parse_all=True)[0]
            except pp.ParseException:
                raise forms.ValidationError(_("Syntax error in expression."))
            if result.complexity > 8:
                raise forms.ValidationError(_("Filter expression exceeds allowed complexity."))
            return result
        return None


class ExpressionFilter(filters.CharFilter):
    field_class = ExpressionFilterField

    def __init__(self, *args, **kwargs):
        kwargs.setdefault(
            "help_text", _("Filter results by using NOT, AND and OR operations on other filters")
        )
        super().__init__(*args, **kwargs)
        self.extra["filter"] = self

    def filter(self, qs, value):
        if value is not None:
            qs = value.evaluate(qs)
        return qs


class BaseFilterSet(filterset.FilterSet):
    """
    Class to override django_filter's FilterSet and provide a way to set help text

    By default, this class will use predefined text and the field name to create help text for the
    filter. However, this can be overriden by setting a help_text dict with the field name
    mapped to some help text:

        help_text = {'name__in': 'Lorem ipsum dolor', 'pulp_last_updated__lt': 'blah blah'}

    """

    help_text = {}
    pulp_id__in = IdInFilter(field_name="pk")
    pulp_href__in = HREFInFilter(field_name="pk")
    q = ExpressionFilter()

    FILTER_DEFAULTS = {
        **filterset.FilterSet.FILTER_DEFAULTS,
        models.OneToOneField: {"filter_class": HyperlinkRelatedFilter},
        models.ForeignKey: {"filter_class": HyperlinkRelatedFilter},
        models.ManyToManyField: {"filter_class": HyperlinkRelatedFilter},
        models.OneToOneRel: {"filter_class": HyperlinkRelatedFilter},
        models.ManyToOneRel: {"filter_class": HyperlinkRelatedFilter},
        models.ManyToManyRel: {"filter_class": HyperlinkRelatedFilter},
    }

    # copied and modified from django_filter.conf
    LOOKUP_EXPR_TEXT = {
        "exact": _("matches"),
        "iexact": _("matches"),
        "contains": _("contains"),
        "icontains": _("contains"),
        "in": _("is in a comma-separated list of"),
        "gt": _("is greater than"),
        "gte": _("is greater than or equal to"),
        "lt": _("is less than"),
        "lte": _("is less than or equal to"),
        "startswith": _("starts with"),
        "istartswith": _("starts with"),
        "endswith": _("ends with"),
        "iendswith": _("ends with"),
        "range": _("is between two comma separated"),
        "isnull": _("has a null"),
        "regex": _("matches regex"),
        "iregex": _("matches regex"),
        "search": _("matches"),
        "ne": _("not equal to"),
    }

    @classmethod
    def get_filters(cls):
        filters = super().get_filters()
        # If we could hook into the Meta mechanism, this would look for cls._meta.ordering_fields
        ordering_fields = []
        if _ordering_fields := getattr(cls, "ordering_fields", None):
            ordering_fields.extend(_ordering_fields)
            try:
                if cls._meta.model:
                    cls._meta.model._meta.get_field("pulp_created")
                    ordering_fields.append(("pulp_created", "pulp_created"))
            except FieldDoesNotExist:
                pass
        elif cls._meta.model:
            ordering_fields.extend(
                (
                    (field.name, field.name)
                    for field in cls._meta.model._meta.get_fields()
                    if not field.is_relation
                )
            )
        ordering_fields.append(("pk", "pk"))
        filters["ordering"] = StableOrderingFilter(fields=tuple(ordering_fields))
        # Properly exclude filter fields if declared so on the Meta class
        if excludes := getattr(cls._meta, "exclude", []):
            for excluded in excludes:
                filters.pop(excluded, None)
        return filters

    @classmethod
    def filter_for_field(cls, field, name, lookup_expr):
        """
        Looks up and initializes a filter and returns it. Also, sets the help text on the filter.

        Args:
            field: The field class for the filter
            name: The name of filter field
            lookup_expr: The lookup expression that specifies how the field is matched
        Returns:
            django_filters.Filter: an initialized Filter object with help text
        """
        f = super().filter_for_field(field, name, lookup_expr)

        if cls.get_filter_name(name, lookup_expr) in cls.help_text:
            f.extra["help_text"] = cls.help_text[cls.get_filter_name(name, lookup_expr)]
        else:
            if lookup_expr in {"range", "in"}:
                val_word = _("values")
            else:
                val_word = _("value")

            f.extra["help_text"] = _("Filter results where {field} {expr} {value}").format(
                field=name, expr=cls.LOOKUP_EXPR_TEXT[lookup_expr], value=val_word
            )

        return f

    def is_valid(self, *args, **kwargs):
        is_valid = super().is_valid(*args, **kwargs)
        DEFAULT_FILTERS = [
            "exclude_fields",
            "fields",
            "limit",
            "minimal",
            "offset",
            "page_size",
            "ordering",
            "format",
        ]
        for field in self.data.keys():
            if field in DEFAULT_FILTERS:
                continue

            if field not in self.filters:
                errors = self.form._errors.get("errors", ErrorList())
                errors.extend(["Invalid Filter: '{field}'".format(field=field)])
                self.form._errors["errors"] = errors
                is_valid = False

        return is_valid


class PulpFilterBackend(DjangoFilterBackend):
    filterset_base = BaseFilterSet

    def get_filterset_class(self, view, queryset=None):
        """Special handling to add PulpTypeInFilter to filters for generic endpoints."""
        filterset_class = super().get_filterset_class(view, queryset=queryset)
        if filterset_class and queryset is not None:
            # Only allow pulp_type filter for generic endpoints
            if hasattr(view, "is_master_viewset") and view.is_master_viewset():

                class PulpTypeFilterSet(filterset_class):
                    pulp_type = PulpTypeFilter(field_name="pulp_type", model=queryset.model)
                    pulp_type__in = PulpTypeInFilter(field_name="pulp_type", model=queryset.model)

                return PulpTypeFilterSet

        return filterset_class


class PulpOpenApiFilterExtension(DjangoFilterExtension):
    target_class = "pulpcore.filters.PulpFilterBackend"

    def _get_schema_from_model_field(self, auto_schema, filter_field, model):
        # Workaround until we can hook into `unambiguous_mapping` of
        # `DjangoFilterExtension.resolve_filter_field`
        if isinstance(filter_field, HyperlinkRelatedFilter):
            return build_basic_type(OpenApiTypes.URI)
        return super()._get_schema_from_model_field(auto_schema, filter_field, model)
