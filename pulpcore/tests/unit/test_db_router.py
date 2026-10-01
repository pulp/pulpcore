import pytest
from django.db import router as django_router

from pulpcore.app.db_router import PulpDomainRouter, _database_alias, is_multi_db_routing_active
from pulpcore.app.models import Domain


@pytest.mark.django_db
def test_database_alias_reads_loaded_field():
    domain = Domain.objects.get(name="default")
    assert _database_alias(domain) == "default"


@pytest.mark.django_db
def test_database_alias_does_not_query_when_field_is_deferred(django_assert_num_queries):
    domain = Domain.objects.only("pk", "name").get(name="default")
    assert "database_alias" not in domain.__dict__, (
        "test setup assumption broken: .only('pk', 'name') should defer 'database_alias'"
    )
    with django_assert_num_queries(0):
        assert _database_alias(domain) == "default"


@pytest.mark.django_db
def test_database_alias_reads_non_default_value_when_loaded():
    domain = Domain.objects.get(name="default")
    domain.__dict__["database_alias"] = "data_1"
    assert _database_alias(domain) == "data_1"


def test_is_multi_db_routing_active_false_by_default():
    # is_multi_db_routing_active() is lru_cache'd (it's a pure function of settings.DATABASE_ROUTERS,
    # fixed for the life of the process in production) -- clear it whenever this test swaps
    # django_router.routers out from under it, in both directions, so neither this test nor a
    # later one sees a stale cached result.
    original_routers = django_router.routers
    try:
        django_router.routers = []
        is_multi_db_routing_active.cache_clear()
        assert is_multi_db_routing_active() is False
    finally:
        django_router.routers = original_routers
        is_multi_db_routing_active.cache_clear()


def test_is_multi_db_routing_active_true_when_registered_then_false_after():
    original_routers = django_router.routers
    try:
        django_router.routers = []
        is_multi_db_routing_active.cache_clear()
        assert is_multi_db_routing_active() is False
        django_router.routers = [PulpDomainRouter()]
        is_multi_db_routing_active.cache_clear()
        assert is_multi_db_routing_active() is True
    finally:
        django_router.routers = original_routers
        is_multi_db_routing_active.cache_clear()
