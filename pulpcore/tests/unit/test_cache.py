import pytest
from time import sleep

import pulpcore.app.redis_connection
from pulpcore.cache import Cache


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
