import json
from time import sleep, time
from uuid import uuid4

import pytest

import pulpcore.app.redis_connection
from pulpcore.app.models import Artifact
from pulpcore.cache import AsyncContentCache, Cache
from pulpcore.responses import ArtifactResponse


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


def _artifact_entry(artifact_pk):
    return json.dumps(
        {
            "type": "ArtifactResponse",
            "artifact_pk": str(artifact_pk),
            "headers": {"X-PULP-ARTIFACT-SIZE": "6"},
            "status": 200,
            "expires": time() + 600,
        }
    )


@pytest.fixture
def stored_entries(monkeypatch, settings):
    """Holds the content cache's entries in a dict instead of Redis."""
    settings.CACHE_ENABLED = True
    entries = {}

    async def get(self, key, base_key=None):
        return entries.get((base_key, key))

    async def delete(self, key=None, base_key=None):
        entries.pop((base_key, key), None)

    monkeypatch.setattr(AsyncContentCache, "get", get)
    monkeypatch.setattr(AsyncContentCache, "delete", delete)
    return entries


@pytest.mark.django_db
@pytest.mark.asyncio
async def test_artifact_entry_is_served_from_cache(stored_entries, tmp_path):
    artifact_path = tmp_path / "file.txt"
    artifact_path.write_text("cached")
    artifact = Artifact.init_and_validate(str(artifact_path))
    await artifact.asave()
    stored_entries[("base", "key")] = _artifact_entry(artifact.pk)

    response = await AsyncContentCache().make_response("key", "base")

    assert isinstance(response, ArtifactResponse)
    assert response._artifact.pk == artifact.pk
    assert response.headers["X-PULP-CACHE"] == "HIT"


@pytest.mark.django_db
@pytest.mark.asyncio
async def test_artifact_entry_for_deleted_artifact_is_a_miss(stored_entries):
    stored_entries[("base", "key")] = _artifact_entry(uuid4())

    response = await AsyncContentCache().make_response("key", "base")

    assert response is None
    assert ("base", "key") not in stored_entries
