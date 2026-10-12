from io import StringIO
from uuid import uuid4

import pytest
from django.conf import settings
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import override_settings

import pulpcore.app.redis_connection
from pulpcore.app.models import Distribution, Repository
from pulpcore.app.util import cache_key
from pulpcore.cache import Cache


@pytest.fixture
def pulp_redisdb(settings, redisdb, monkeypatch):
    monkeypatch.setattr(pulpcore.app.redis_connection, "_conn", None)
    monkeypatch.setattr(pulpcore.app.redis_connection, "_a_conn", None)
    settings.CACHE_ENABLED = True
    settings.REDIS_URL = "unix://" + redisdb.get_connection_kwargs()["path"]
    return redisdb


@pytest.fixture
def repository(db):
    return Repository.objects.create(name=str(uuid4()))


@pytest.fixture
def distributions(repository):
    return [
        Distribution.objects.create(
            name=str(uuid4()), base_path=str(uuid4()), repository=repository
        ),
        Distribution.objects.create(name=str(uuid4()), base_path=str(uuid4())),
    ]


@pytest.mark.django_db
def test_clear_cache(pulp_redisdb, distributions):
    cache = Cache()
    for distribution in distributions:
        cache.set("key", "value", base_key=cache_key(distribution.base_path))

    out = StringIO()
    call_command("clear-cache", stdout=out)

    assert (
        cache.exists(base_key=[cache_key(distribution.base_path) for distribution in distributions])
        == 0
    )
    assert out.getvalue().strip() == "Cleared 2 cache entries."


@pytest.mark.django_db
@pytest.mark.parametrize("use_prn", [False, True])
def test_clear_cache_for_repository(pulp_redisdb, repository, distributions, use_prn):
    cache = Cache()
    for distribution in distributions:
        cache.set("key", "value", base_key=cache_key(distribution.base_path))

    repository_selector = f"prn:core.repository:{repository.pk}" if use_prn else repository.name
    call_command("clear-cache", repository=repository_selector)

    assert not cache.exists(base_key=cache_key(distributions[0].base_path))
    assert cache.exists(base_key=cache_key(distributions[1].base_path))


@pytest.mark.django_db
@pytest.mark.parametrize("use_prn", [False, True])
def test_clear_cache_for_distribution(pulp_redisdb, distributions, use_prn):
    cache = Cache()
    for distribution in distributions:
        cache.set("key", "value", base_key=cache_key(distribution.base_path))

    distribution_selector = (
        f"prn:core.distribution:{distributions[1].pk}" if use_prn else distributions[1].name
    )
    call_command("clear-cache", distribution=distribution_selector)

    assert cache.exists(base_key=cache_key(distributions[0].base_path))
    assert not cache.exists(base_key=cache_key(distributions[1].base_path))


@pytest.mark.django_db
def test_clear_cache_for_base_path(pulp_redisdb):
    cache = Cache()
    base_key = cache_key("base-path")
    other_base_key = cache_key("other-base-path")
    cache.set("key", "value", base_key=base_key)
    cache.set("key", "value", base_key=other_base_key)

    out = StringIO()
    command_options = {"base_path": "base-path", "stdout": out}
    if settings.DOMAIN_ENABLED:
        command_options["domain"] = "default"
    call_command("clear-cache", **command_options)

    assert not cache.exists(base_key=base_key)
    assert cache.exists(base_key=other_base_key)
    assert out.getvalue().strip() == "Cleared 1 cache entry."


@pytest.mark.django_db
@override_settings(DOMAIN_ENABLED=True)
def test_clear_cache_for_base_path_with_domain(pulp_redisdb):
    cache = Cache()
    default_base_key = cache_key("base-path", domain="default")
    other_base_key = cache_key("base-path", domain="other")
    cache.set("key", "value", base_key=default_base_key)
    cache.set("key", "value", base_key=other_base_key)

    call_command("clear-cache", base_path="base-path", domain="default")

    assert not cache.exists(base_key=default_base_key)
    assert cache.exists(base_key=other_base_key)


@pytest.mark.django_db
@override_settings(DOMAIN_ENABLED=True)
def test_clear_cache_for_base_path_requires_domain(pulp_redisdb):
    with pytest.raises(CommandError, match="--domain is required"):
        call_command("clear-cache", base_path="base-path")
