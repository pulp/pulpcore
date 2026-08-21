from time import sleep
from unittest.mock import Mock

import pytest

import pulpcore.app.redis_connection
from pulpcore.cache import AsyncContentCache, Cache, CacheKeys, accept_prefers_json


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


@pytest.mark.parametrize(
    "accept_header,expected",
    [
        (None, False),
        ("", False),
        ("*/*", False),
        ("text/html", False),
        ("text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8", False),
        ("application/json, text/html", True),
        ("text/html, application/json", False),
        ("application/json", True),
        ("Application/JSON", True),
        ("application/vnd.pypi.simple.v1+json", True),
        ("application/json;q=0.5, text/html", False),
        ("application/json;q=0.9, text/html;q=0.8", True),
        ("application/json;q=0", False),
        ("application/json;charset=utf-8", True),
        ("text/html;q=0.9, application/json;q=0.9", False),
        ("  application/json  ", True),
        (Mock(), False),
        (1, False),
    ],
)
def test_accept_prefers_json(accept_header, expected):
    assert accept_prefers_json(accept_header) is expected


def test_content_cache_key_varies_by_accept(monkeypatch):
    """JSON and HTML requests for the same path must not share a cache key."""
    monkeypatch.setattr("pulpcore.cache.cache.get_async_redis_connection", lambda: None)
    cache = AsyncContentCache(keys=(CacheKeys.path, CacheKeys.method, CacheKeys.format))

    def make_request(accept):
        request = Mock()
        request.path = "/pulp/content/foo/"
        request.method = "GET"
        request.url.host = "example.com"
        request.headers = {} if accept is None else {"Accept": accept}
        return request

    json_key = cache.make_key(make_request("application/json"))
    html_key = cache.make_key(make_request("text/html"))
    default_key = cache.make_key(make_request(None))
    star_key = cache.make_key(make_request("*/*"))

    assert json_key == "/pulp/content/foo/:GET:json"
    assert html_key == "/pulp/content/foo/:GET:other"
    assert default_key == html_key
    assert star_key == html_key
    assert json_key != html_key


def test_content_cache_key_varies_by_query(monkeypatch):
    """JSON pagination params must be in the cache key; junk query params and HTML must not."""
    monkeypatch.setattr("pulpcore.cache.cache.get_async_redis_connection", lambda: None)
    cache = AsyncContentCache(
        keys=(CacheKeys.path, CacheKeys.method, CacheKeys.format, CacheKeys.query)
    )

    def make_request(accept, query=None):
        request = Mock()
        request.path = "/pulp/content/foo/"
        request.method = "GET"
        request.url.host = "example.com"
        request.headers = {"Accept": accept}
        request.query = {} if query is None else query
        return request

    page0 = cache.make_key(make_request("application/json", {"limit": "1", "offset": "0"}))
    page0_reordered = cache.make_key(
        make_request("application/json", {"offset": "0", "limit": "1"})
    )
    page1 = cache.make_key(make_request("application/json", {"limit": "1", "offset": "1"}))
    no_query = cache.make_key(make_request("application/json", {}))
    junk = cache.make_key(make_request("application/json", {"t": "12345", "foo": "bar"}))
    html_junk = cache.make_key(make_request("text/html", {"t": "12345", "limit": "1"}))
    html_plain = cache.make_key(make_request("text/html", {}))

    assert page0 == "/pulp/content/foo/:GET:json:1:0"
    assert page0_reordered == page0
    assert page1 == "/pulp/content/foo/:GET:json:1:1"
    assert no_query == "/pulp/content/foo/:GET:json:1000:0"
    assert junk == no_query
    assert html_junk == html_plain
    assert html_plain == "/pulp/content/foo/:GET:other"
    assert page0 != page1
