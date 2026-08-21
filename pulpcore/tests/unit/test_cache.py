import json
from time import sleep
from time import time as now
from unittest.mock import AsyncMock, Mock

import pytest
from aiohttp.web import Response
from aiohttp.web_exceptions import HTTPNotModified
from django.test import override_settings
from django.utils.http import http_date

import pulpcore.app.redis_connection
from pulpcore.cache import Cache
from pulpcore.cache.cache import AsyncContentCache


@pytest.fixture
def pulp_redisdb(settings, redisdb, monkeypatch):
    monkeypatch.setattr(pulpcore.app.redis_connection, "_conn", None)
    monkeypatch.setattr(pulpcore.app.redis_connection, "_a_conn", None)
    settings.CACHE_ENABLED = True
    settings.REDIS_URL = "unix://" + redisdb.get_connection_kwargs()["path"]
    return redisdb


def test_basic_set_get(pulp_redisdb):
    """Tests setting value, then getting it"""
    cache = Cache()
    cache.set("key", "hello")
    ret = cache.get("key")
    assert ret == b"hello"
    cache.set("key", "there")
    ret = cache.get("key")
    assert ret == b"there"


def test_basic_exists(pulp_redisdb):
    """Tests that keys already set exist"""
    cache = Cache()
    cache.set("key", "hello")
    assert cache.exists("key")
    assert not cache.exists("absent")


def test_basic_delete(pulp_redisdb):
    """Tests deleting value"""
    cache = Cache()
    cache.set("key", "hello")
    assert cache.exists("key")
    cache.delete("key")
    ret = cache.get("key")
    assert ret is None


def test_basic_expires(pulp_redisdb):
    """Tests setting values with expiration times"""
    cache = Cache()
    cache.set("key", "hi", expires=2)
    ret = cache.get("key")
    assert ret == b"hi"
    sleep(3)
    ret = cache.get("key")
    assert ret is None


def test_group_with_base_key(pulp_redisdb):
    """Tests grouping multiple key-values under one base-key"""
    cache = Cache()
    tuples = [
        ("key1", "hi", "base1"),
        ("key2", "friends", "base1"),
        ("key1", "hola", "base2"),
        ("key2", "amigos", "base2"),
    ]
    for key, value, base_key in tuples:
        cache.set(key, value, base_key=base_key)
    for key, value, base_key in tuples:
        assert value.encode() == cache.get(key, base_key=base_key)

    dict1 = {a.encode(): b.encode() for a, b, _ in tuples[:2]}
    dict2 = {a.encode(): b.encode() for a, b, _ in tuples[2:]}
    assert cache.get(None, base_key="base1") == dict1
    assert cache.get(None, base_key="base2") == dict2
    assert cache.exists(base_key="base1")
    assert cache.exists(base_key="base2")
    assert cache.exists(base_key=["base1", "base2"]) == 2


def test_delete_base_key(pulp_redisdb):
    """Tests deleting multiple key-values under one base-key"""
    cache = Cache()
    cache.delete(base_key="base1")
    assert not cache.exists("key1", base_key="base1")
    assert not cache.exists("key2", base_key="base1")
    assert not cache.exists(base_key="base1")

    cache.set("key1", "hi", base_key="base1")
    assert cache.exists("key1", base_key="base1")
    # multi delete
    cache.delete(base_key=["base1", "base2"])
    assert cache.exists(base_key=["base1", "base2"]) == 0


def test_clear(pulp_redisdb):
    """Tests clearing the cache"""
    cache = Cache()
    tuples = [
        ("key", "hi", None),
        ("key1", "there", None),
        ("key", "hey", "base"),
        ("key1", "now", "base"),
    ]
    for key, value, base_key in tuples:
        cache.set(key, value, base_key=base_key)
    cache.redis.flushdb()
    for key, _, base_key in tuples:
        assert not cache.exists(key, base_key=base_key)


def _request_with_if_modified_since(value):
    return Mock(headers={"If-Modified-Since": value} if value else {})


_LM = http_date(1_000_000_000)


def test_async_content_cache_not_modified():
    """If-Modified-Since is compared to Last-Modified at second resolution."""
    newer = http_date(1_000_000_060)
    older = http_date(999_999_940)
    future = http_date(now() + 86400)
    inm = Mock(headers={"If-Modified-Since": _LM, "If-None-Match": '"abc"'})

    assert AsyncContentCache._not_modified(_request_with_if_modified_since(_LM), _LM) is True
    assert AsyncContentCache._not_modified(_request_with_if_modified_since(newer), _LM) is True
    assert AsyncContentCache._not_modified(_request_with_if_modified_since(older), _LM) is False
    assert AsyncContentCache._not_modified(_request_with_if_modified_since(None), _LM) is False
    assert AsyncContentCache._not_modified(_request_with_if_modified_since(_LM), None) is False
    assert AsyncContentCache._not_modified(_request_with_if_modified_since("garbage"), _LM) is False
    assert AsyncContentCache._not_modified(inm, _LM) is False
    assert AsyncContentCache._not_modified(_request_with_if_modified_since(future), _LM) is False


def test_async_content_cache_make_not_modified_echoes_metadata():
    """The 304 carries only validator/caching metadata already present on the source."""
    source = {
        "Cache-Control": "public, max-age=0, must-revalidate",
        "Content-Length": "1024",
        "X-PULP-CACHE": "HIT",
    }

    exc = AsyncContentCache._make_not_modified(source, _LM)

    assert isinstance(exc, HTTPNotModified)
    assert exc.headers["Last-Modified"] == _LM
    assert exc.headers["Cache-Control"] == "public, max-age=0, must-revalidate"
    assert exc.headers["X-PULP-CACHE"] == "HIT"
    assert "Content-Length" not in exc.headers

    bare = AsyncContentCache._make_not_modified({}, _LM)
    assert "X-PULP-CACHE" not in bare.headers
    assert "Cache-Control" not in bare.headers


def test_async_content_cache_build_response_pops_last_modified():
    """build_response must not pass the stored last_modified field to the response constructor."""
    cache = AsyncContentCache.__new__(AsyncContentCache)
    entry = {
        "type": "Response",
        "status": 200,
        "headers": {"Last-Modified": _LM},
        "last_modified": _LM,
        "body": b"hello".hex(),
    }

    response = cache.build_response(entry)

    assert response.status == 200
    assert response.body == b"hello"
    assert response.headers["Last-Modified"] == _LM
    assert response.headers["X-PULP-CACHE"] == "HIT"


def _entry(*, store_field=True):
    entry = {
        "type": "Response",
        "status": 200,
        "headers": {
            "Last-Modified": _LM,
            "Cache-Control": "public, max-age=0, must-revalidate",
        },
        "body": b"payload".hex(),
        "expires": None,
    }
    if store_field:
        entry["last_modified"] = _LM
    return entry


def _cache():
    cache = AsyncContentCache.__new__(AsyncContentCache)
    cache.auth = None
    cache.default_base_key = "base"
    cache.keys = ()
    cache.default_expires_ttl = 60
    cache.get_request_from_args = lambda args: args[0]
    cache.make_key = lambda req: "key"
    return cache


async def _run_cached(cache, request, handler=None):
    if handler is None:

        async def handler(req):
            raise AssertionError("handler must not run")

    with override_settings(CACHE_ENABLED=True):
        return await AsyncContentCache.__call__(cache, handler)(request)


@pytest.mark.asyncio
@pytest.mark.parametrize("store_field", [True, False], ids=["stored-field", "header-fallback"])
async def test_cache_hit_304_does_not_rebuild_response(store_field):
    """A matching If-Modified-Since 304s without reconstructing the cached response."""
    cache = _cache()
    cache.get_entry = AsyncMock(return_value=_entry(store_field=store_field))
    cache.build_response = Mock(side_effect=AssertionError("must not reconstruct"))

    with pytest.raises(HTTPNotModified) as exc:
        await _run_cached(cache, Mock(headers={"If-Modified-Since": _LM}))

    cache.build_response.assert_not_called()
    assert exc.value.headers["Last-Modified"] == _LM
    assert exc.value.headers["X-PULP-CACHE"] == "HIT"


@pytest.mark.asyncio
async def test_cache_hit_stale_if_modified_since_rebuilds_response():
    """An older If-Modified-Since on a cache hit still reconstructs the full cached response."""
    entry = _entry()
    rebuilt = Mock(headers={"X-PULP-ARTIFACT-SIZE": None})
    cache = _cache()
    cache.get_entry = AsyncMock(return_value=entry)
    cache.build_response = Mock(return_value=rebuilt)

    response = await _run_cached(cache, Mock(headers={"If-Modified-Since": http_date(999_999_000)}))

    cache.build_response.assert_called_once_with(entry)
    assert response is rebuilt


@pytest.mark.asyncio
async def test_cache_miss_does_not_304_prepared_stream():
    """A live stream that already started writing must not be converted into a 304."""
    stream = Mock(headers={"Last-Modified": _LM}, prepared=True, status=200)
    cache = _cache()
    cache.get_entry = AsyncMock(return_value=None)
    cache.make_entry = AsyncMock(return_value=stream)

    async def handler(req):
        raise AssertionError("handler is invoked via make_entry")

    assert await _run_cached(cache, Mock(headers={"If-Modified-Since": _LM}), handler) is stream


@pytest.mark.asyncio
async def test_make_entry_does_not_cache_304():
    """HTTPNotModified is HTTPSuccessful but must never be written to Redis."""
    cache = _cache()
    cache.set = AsyncMock()

    async def handler():
        raise HTTPNotModified(headers={"Last-Modified": _LM})

    with pytest.raises(HTTPNotModified):
        await cache.make_entry("k", "b", handler, (), {}, 60)

    cache.set.assert_not_called()


@pytest.mark.asyncio
async def test_make_entry_stores_last_modified():
    """A 200 with Last-Modified is stored so later cache hits can 304 without rebuilding."""
    captured = {}
    cache = _cache()

    async def fake_set(key, value, expires=None, base_key=None):
        captured["entry"] = json.loads(value)

    cache.set = fake_set

    async def handler():
        return Response(body=b"hello", headers={"Last-Modified": _LM})

    result = await cache.make_entry("k", "b", handler, (), {}, 60)

    assert result.headers["Last-Modified"] == _LM
    assert result.headers["X-PULP-CACHE"] == "MISS"
    assert captured["entry"]["last_modified"] == _LM
    assert captured["entry"]["headers"]["Last-Modified"] == _LM
    assert captured["entry"]["type"] == "Response"
