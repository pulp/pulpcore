import pytest
from django.db import router as django_router

from pulpcore.app.db_router import PulpDomainRouter, _database_alias, is_multi_db_routing_active
from pulpcore.app.models import Domain


@pytest.mark.django_db
def test_database_alias_reads_loaded_field():
    """The common case: `database_alias` is already loaded, so the plain `__dict__` lookup
    returns it directly (no query, whether one would even be needed or not)."""
    domain = Domain.objects.get(name="default")
    assert _database_alias(domain) == "default"


@pytest.mark.django_db
def test_database_alias_does_not_query_when_field_is_deferred(django_assert_num_queries):
    """Regression test for the `getattr(domain, "database_alias", "default")` review question
    (see `_database_alias`'s docstring): a `Domain` instance fetched with `database_alias`
    deferred (`.only(...)` excluding it) must resolve through `_database_alias()` with **zero**
    queries, not silently trigger a `refresh_from_db()` the way a bare `getattr()`/`hasattr()`
    would via `DeferredAttribute.__get__`.

    Every current call site (`DomainMiddleware`'s plain `.get()`, and the `select_related
    ("pulp_domain")` fetches on the task/worker paths) happens to always load the full row
    today, so this specific deferred-field shape doesn't occur in practice yet -- this test
    guards against a future caller reintroducing it silently.
    """
    domain = Domain.objects.only("pk", "name").get(name="default")
    assert "database_alias" not in domain.__dict__, (
        "test setup assumption broken: .only('pk', 'name') should defer 'database_alias'"
    )
    with django_assert_num_queries(0):
        # Falls back to "default" without ever touching the DB -- see docstring: this can't
        # recurse into the router (Domain is control-plane, pinned to "default" regardless),
        # but it would still be a wasted, silent query on every call if not guarded.
        assert _database_alias(domain) == "default"


@pytest.mark.django_db
def test_database_alias_reads_non_default_value_when_loaded():
    """Sanity check that the helper isn't just hardcoding `"default"` -- it actually reads
    whatever value is present in `__dict__`, for any domain/alias name."""
    domain = Domain.objects.get(name="default")
    domain.__dict__["database_alias"] = "data_1"
    assert _database_alias(domain) == "data_1"


def test_is_multi_db_routing_active_false_by_default():
    """The test suite's own settings don't register PulpDomainRouter (single-DB is still the
    common case), so this must be False without any override -- also guards against the
    previous, now-removed `len(settings.DATABASES) > 1` proxy silently coming back."""
    assert is_multi_db_routing_active() is False


def test_is_multi_db_routing_active_true_when_registered_then_false_after():
    """Once a deployment explicitly registers `PulpDomainRouter` in `DATABASE_ROUTERS` (the only
    way it's ever active now -- see `db_router.py`'s module docstring), this must reflect that
    immediately, and revert just as immediately once unregistered again.

    Deliberately does *not* use `django.test.override_settings(DATABASE_ROUTERS=...)` here: this
    codebase's dynaconf/Django integration (`pulpcore.app.settings`'s `DjangoDynaconf(__name__)`
    call) monkey-patches `sys.modules["django.conf"]` with a wrapper that serves a *different*
    `LazySettings` instance than the one Django's own internals bind at import time -- in
    particular, `django.db.utils` (and so the global `django.db.router` singleton) resolves
    `from django.conf import settings` to the original, unpatched object, which
    `override_settings` never touches. So mutating `DATABASE_ROUTERS` via `override_settings`
    silently never reaches the actual router registry this test needs to exercise (confirmed via
    manual reproduction: `django.db.router.routers` stayed `[]` throughout the override block).
    This doesn't affect production, which only ever sets `DATABASE_ROUTERS` once, at process
    startup via a `PULP_DATABASE_ROUTERS` env var, before that divergence has a chance to matter.
    So: exercise the actual mechanism `is_multi_db_routing_active()` depends on directly --
    `django.db.router.routers`, the live, already-resolved router instance list -- the same way
    Django's own `ConnectionRouter._route_db` consults it on every query.
    """
    assert is_multi_db_routing_active() is False
    original_routers = django_router.routers
    try:
        django_router.routers = [PulpDomainRouter()]
        assert is_multi_db_routing_active() is True
    finally:
        django_router.routers = original_routers
    assert is_multi_db_routing_active() is False
