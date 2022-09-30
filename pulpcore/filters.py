from gettext import gettext as _

from django.forms.utils import ErrorList
from django_filters.rest_framework.filters import OrderingFilter
from django_filters.rest_framework import DjangoFilterBackend, filterset
from django.core.exceptions import FieldDoesNotExist

from drf_spectacular.contrib.django_filters import DjangoFilterExtension


class StableOrderingFilter(OrderingFilter):
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


class BaseFilterSet(filterset.FilterSet):
    """
    Class to override django_filter's FilterSet and provide a way to set help text

    By default, this class will use predefined text and the field name to create help text for the
    filter. However, this can be overriden by setting a help_text dict with the field name
    mapped to some help text:

        help_text = {'name__in': 'Lorem ipsum dolor', 'pulp_last_updated__lt': 'blah blah'}

    """

    help_text = {}

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
                ((field.name, field.name) for field in cls._meta.model._meta.get_fields())
            )
        ordering_fields.append(("pk", "pk"))
        filters["ordering"] = StableOrderingFilter(fields=tuple(ordering_fields))
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


class PulpOpenApiFilterExtension(DjangoFilterExtension):
    target_class = "pulpcore.filters.PulpFilterBackend"
