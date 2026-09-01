from django.db import models
from django.db.models import Q


class CrossDBQuerySetMixin:
    def filter(self, *args, **kwargs):
        from pulpcore.app.db_router import is_multi_db_routing_active

        if not is_multi_db_routing_active():
            return super().filter(*args, **kwargs)
        args = tuple(self._resolve_cross_db_q(a) if isinstance(a, Q) else a for a in args)
        self._resolve_cross_db_kwargs(kwargs)
        return super().filter(*args, **kwargs)

    def exclude(self, *args, **kwargs):
        from pulpcore.app.db_router import is_multi_db_routing_active

        if not is_multi_db_routing_active():
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
