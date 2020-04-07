from django.core.exceptions import FieldDoesNotExist
from rest_framework.filters import OrderingFilter


class StableOrderingFilter(OrderingFilter):
    """
    Ordering filter backend.

    Reference: https://github.com/encode/django-rest-framework/issues/6886#issuecomment-547120480
    """

    def get_ordering(self, request, queryset, view):
        """
        Ordering is set by a comma delimited ?ordering=... query parameter.

        The `ordering` query parameter can be overridden by setting
        the `ordering_param` value on the OrderingFilter or by
        specifying an `ORDERING_PARAM` value in the API settings.
        """
        ordering = super(StableOrderingFilter, self).get_ordering(request, queryset, view)
        try:
            field = queryset.model._meta.get_field("pulp_created")
        except FieldDoesNotExist:
            field = queryset.model._meta.pk

        if ordering is None:
            return ["-" + field.name]

        return list(ordering) + ["-" + field.name]
