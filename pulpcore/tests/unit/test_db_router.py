import pytest

from pulpcore.app.db_router import _database_alias
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
