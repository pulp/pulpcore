from time import sleep
from django.test import TestCase
from unittest import skipUnless

from pulpcore.cache import Cache, ConnectionError


try:
    is_redis_connected = Cache().redis.ping()
except (ConnectionError, AttributeError):
    is_redis_connected = False


@skipUnless(is_redis_connected, "Could not connect to the Redis server")
class CacheBasicOperationsTestCase(TestCase):
    """Tests the basic APIs of the Cache object"""

    def test_01_basic_set_get(self):
        """Tests setting value, then getting it"""
        cache = Cache()
        cache.set("key", "hello")
        ret = cache.get("key")
        self.assertEqual(ret, b"hello")
        cache.set("key", "there")
        ret = cache.get("key")
        self.assertEqual(ret, b"there")

    def test_02_basic_exists(self):
        """Tests that keys already set exist"""
        cache = Cache()
        self.assertTrue(cache.exists("key"))
        self.assertFalse(cache.exists("absent"))

    def test_03_basic_delete(self):
        """Tests deleting value"""
        cache = Cache()
        self.assertTrue(cache.exists("key"))
        cache.delete("key")
        ret = cache.get("key")
        self.assertIsNone(ret)

    def test_04_basic_expires(self):
        """Tests setting values with expiration times"""
        self.skipTest("Timing is inconsistent in CI")
        cache = Cache()
        cache.set("key", "hi", expires=5)
        ret = cache.get("key")
        self.assertEqual(ret, b"hi")
        sleep(5)
        ret = cache.get("key")
        self.assertIsNone(ret)

    def test_05_group_with_base_key(self):
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
            self.assertEqual(value.encode(), cache.get(key, base_key=base_key))

        dict1 = {a.encode(): b.encode() for a, b, _ in tuples[:2]}
        dict2 = {a.encode(): b.encode() for a, b, _ in tuples[2:]}
        self.assertDictEqual(dict1, cache.get(None, base_key="base1"))
        self.assertDictEqual(dict2, cache.get(None, base_key="base2"))
        self.assertTrue(cache.exists(base_key="base1"))
        self.assertTrue(cache.exists(base_key="base2"))
        self.assertEqual(2, cache.exists(base_key=["base1", "base2"]))

    def test_06_delete_base_key(self):
        """Tests deleting multiple key-values under one base-key"""
        cache = Cache()
        cache.delete(base_key="base1")
        self.assertFalse(cache.exists("key1", base_key="base1"))
        self.assertFalse(cache.exists("key2", base_key="base1"))
        self.assertFalse(cache.exists(base_key="base1"))

        cache.set("key1", "hi", base_key="base1")
        self.assertTrue(cache.exists("key1", base_key="base1"))
        # multi delete
        cache.delete(base_key=["base1", "base2"])
        self.assertEqual(0, cache.exists(base_key=["base1", "base2"]))

    def test_07_clear(self):
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
            self.assertFalse(cache.exists(key, base_key=base_key))
