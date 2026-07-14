"""
Layer 2 of the query architecture: cross-database-safe subquery resolution.

Django compiles `queryset.filter(field__in=other_queryset)` (or a `Q(...)` containing a nested
queryset) as a SQL subquery. That fails outright when `other_queryset` and the outer queryset
live on two different physical PostgreSQL instances -- there is no way for one Postgres server
to run a subquery against rows that live on a different server. The clearest example is RBAC:
`role_util.get_objects_for_user_roles()` builds `Q(pk_str__in=user_role_pks)` where
`user_role_pks` is a lazy `UserRole` queryset (control-plane, always `default`) and the outer
queryset is a data-plane model that may be routed to a satellite (KI-01, KI-25).

`CrossDBQuerySetMixin` detects exactly this situation -- a queryset-valued kwarg/`Q` child whose
`.db` differs from the outer queryset's `.db` -- and materializes it with `list()` before letting
the normal `filter()`/`exclude()` machinery run, at which point Django emits an `IN (values...)`
clause instead of a subquery. For single-database deployments `value.db != self.db` is always
`False`, so the fast-path below (`len(settings.DATABASES) <= 1`) skips the extra work entirely
and every one of Django's original semantics/optimizations are preserved -- see the design doc's
Feasibility & Impact Assessment §1 for why that fast path matters (a permanent unconditional tax
on `.filter()`/`.exclude()` for every install otherwise, most of whom never configure a second
database).
"""

from django.conf import settings
from django.db import models
from django.db.models import Q


class CrossDBQuerySetMixin:
    """
    Mix into any base `QuerySet` class whose `.filter()`/`.exclude()` calls might receive a
    queryset (directly, or nested in a `Q()`) that lives on a different database alias than
    `self`. Safe to mix into every queryset unconditionally: the `len(settings.DATABASES) <= 1`
    fast path makes this a no-op for the common single-database case.
    """

    def filter(self, *args, **kwargs):
        if len(settings.DATABASES) <= 1:
            return super().filter(*args, **kwargs)
        args = tuple(self._resolve_cross_db_q(a) if isinstance(a, Q) else a for a in args)
        self._resolve_cross_db_kwargs(kwargs)
        return super().filter(*args, **kwargs)

    def exclude(self, *args, **kwargs):
        if len(settings.DATABASES) <= 1:
            return super().exclude(*args, **kwargs)
        args = tuple(self._resolve_cross_db_q(a) if isinstance(a, Q) else a for a in args)
        self._resolve_cross_db_kwargs(kwargs)
        return super().exclude(*args, **kwargs)

    def _resolve_cross_db_kwargs(self, kwargs):
        for key, value in list(kwargs.items()):
            if isinstance(value, models.QuerySet) and value.db != self.db:
                kwargs[key] = list(value)

    def _resolve_cross_db_q(self, q):
        for i, child in enumerate(q.children):
            if isinstance(child, Q):
                self._resolve_cross_db_q(child)
            elif isinstance(child, tuple):
                key, value = child
                if isinstance(value, models.QuerySet) and value.db != self.db:
                    q.children[i] = (key, list(value))
        return q
