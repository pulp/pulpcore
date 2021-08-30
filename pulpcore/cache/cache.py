import enum
import json

from aiohttp.web import FileResponse, Response, HTTPSuccessful, Request
from aiohttp.web_exceptions import HTTPFound

from pulpcore.app.settings import settings
from pulpcore.app.redis_connection import get_redis_connection, get_async_redis_connection

DEFAULT_EXPIRES_TTL = settings.CACHE_SETTINGS["EXPIRES_TTL"]


class CacheKeys(enum.Enum):
    """Available keys to construct the index key for cache entry."""

    path = "path"
    host = "host"
    method = "method"


class Cache:
    """Base class for Pulp's cache"""

    default_base_key = "PULP_CACHE"
    default_expires_ttl = DEFAULT_EXPIRES_TTL

    def __init__(self):
        """Creates synchronous cache instance"""
        self.redis = get_redis_connection()

    def get(self, key, base_key=None):
        """Gets cached entry of key"""
        base_key = base_key or self.default_base_key
        if key is None:
            return self.redis.hgetall(base_key)
        return self.redis.hget(base_key, key)

    def set(self, key, value, expires=None, base_key=None):
        """Sets the cached entry at key"""
        base_key = base_key or self.default_base_key
        ret = self.redis.hset(base_key, key, value)
        if expires:
            self.redis.expire(base_key, expires)
        return ret

    def exists(self, key=None, base_key=None):
        """Checks if cached entries exist"""
        if not base_key and base_key is not None:
            return False  # Failsafe for passing empty list/str
        base_key = base_key or self.default_base_key
        if key:
            return self.redis.hexists(base_key, key)
        else:
            if isinstance(base_key, str):
                base_key = [base_key]
            return self.redis.exists(*base_key)

    def delete(self, key=None, base_key=None):
        """
        Deletes the cached entry at base_key: key

        If only base_key is supplied then delete all entries under that base_key
        key can be a list to delete multiple entries under a base_key
        base_key can be a list to delete multiple sets of entries
        key and base_key should not both be lists
        """
        base_key = base_key or self.default_base_key
        if key:
            return self.redis.hdel(base_key, key)
        if isinstance(base_key, str):
            base_key = [base_key]
        return self.redis.delete(*base_key)


class AsyncCache:
    """Base class for asynchronous Pulp Cache"""

    default_base_key = "PULP_CACHE"
    default_expires_ttl = DEFAULT_EXPIRES_TTL

    def __init__(self):
        """Creates asynchronous cache instance"""
        self.redis = get_async_redis_connection()

    async def get(self, key, base_key=None):
        """Gets cached entry of key"""
        base_key = base_key or self.default_base_key
        if key is None:
            return await self.redis.hgetall(base_key)
        return await self.redis.hget(base_key, key)

    async def set(self, key, value, expires=None, base_key=None):
        """Sets the cached entry at key"""
        base_key = base_key or self.default_base_key
        ret = await self.redis.hset(base_key, key, value)
        if expires:
            await self.redis.expire(base_key, expires)
        return ret

    async def exists(self, key=None, base_key=None):
        """Checks if cached entries exist"""
        if not base_key and base_key is not None:
            return False  # Failsafe for passing empty list/str
        base_key = base_key or self.default_base_key
        if key:
            return await self.redis.hexists(base_key, key)
        else:
            if isinstance(base_key, str):
                base_key = [base_key]
            return await self.redis.exists(*base_key)

    async def delete(self, key=None, base_key=None):
        """
        Deletes the cached entry at base_key: key

        If only base_key is supplied then delete all entries under that base_key
        key can be a list to delete multiple entries under a base_key
        base_key can be a list to delete multiple sets of entries
        key and base_key should not both be lists
        """
        base_key = base_key or self.default_base_key
        if key:
            return await self.redis.hdel(base_key, key)
        if isinstance(base_key, str):
            base_key = [base_key]
        return await self.redis.delete(*base_key)


class ContentCache(AsyncCache):
    """Cache object meant to be used for the content app"""

    RESPONSE_TYPES = {
        "FileResponse": FileResponse,
        "Response": Response,
        "Redirect": HTTPFound,
    }

    def __init__(self, base_key=None, expires_ttl=None, keys=None, auth=None):
        """
        Initiates a cache instance to be used for dealing with an aiohttp server

        Args:
            base_key: a string to group entries under, defaults to DEFAULT_BASE_KEY,
                      can be a callable taking the request and cache instance as arguments
            expires_ttl: length in seconds entries should live in the cache, EXPIRES_TTL is default
            keys: a list of CacheKeys to use for key creation upon entry placement, path is default
            auth: a callable to check authorization of the request; takes the request, cache
                  instance, and base_key as arguments.
        """
        super().__init__()
        self.default_base_key = base_key or self.default_base_key
        self.keys = keys or (CacheKeys.path,)
        self.default_expires_ttl = expires_ttl or self.default_expires_ttl
        self.auth = auth

    def __call__(self, func):
        """Decorator magic call to make the handler cached"""
        if not settings.CACHE_ENABLED:
            return func

        async def cached_function(*args):
            request = self.get_request_from_args(args)
            bk = self.default_base_key
            if callable(self.default_base_key):
                bk = await self.default_base_key(request, self)
            if self.auth:
                await self.auth(request, self, bk)
            key = self.make_key(request)
            # Check cache
            response = await self.make_response(key, bk)
            if response is None:
                # Cache miss, create new entry
                response = await self.make_entry(key, bk, func, args, self.default_expires_ttl)
            return response

        return cached_function

    def get_request_from_args(self, args):
        """Finds the request object from list of args"""
        for arg in args:
            if isinstance(arg, Request):
                return arg

    async def make_response(self, key, base_key):
        """Tries to find the cached entry and turn it into a proper response"""
        entry = await self.get(key, base_key)
        if not entry:
            return None
        entry = json.loads(entry)
        response_type = entry.pop("type", None)
        if not response_type or response_type not in self.RESPONSE_TYPES:
            # Bad entry, delete from cache
            self.delete(key, base_key)
            return None
        response = self.RESPONSE_TYPES[response_type](**entry)
        response.headers.update({"X-PULP-CACHE": "HIT"})
        return response

    async def make_entry(self, key, base_key, handler, args, expires=86400):
        """Gets the response for the request and try to turn it into a cacheable entry"""
        try:
            response = await handler(*args)
        except (HTTPSuccessful, HTTPFound) as e:
            response = e

        entry = {"headers": dict(response.headers), "status": response.status}
        response.headers.update({"X-PULP-CACHE": "MISS"})
        if isinstance(response, FileResponse):
            entry["path"] = str(response._path)
            entry["type"] = "FileResponse"
        elif isinstance(response, (Response, HTTPSuccessful)):
            body = response.body
            entry["text"] = getattr(body, "_value", body).decode("utf-8")
            entry["type"] = "Response"
        elif isinstance(response, HTTPFound):
            entry["location"] = str(response.location)
            entry["type"] = "Redirect"
        else:
            # We don't cache StreamResponses or errors
            return response

        # TODO look into smaller format, maybe some compression on the text
        await self.set(key, json.dumps(entry), expires, base_key=base_key)
        return response

    def make_key(self, request):
        """Makes the key based off the request"""
        # Might potentially have to make this async if keys require async data from request
        all_keys = {
            CacheKeys.path: request.match_info["path"],
            CacheKeys.method: request.method,
            CacheKeys.host: request.url.host,
        }
        key = ":".join(all_keys[k] for k in self.keys)
        return key


# TODO Add Cache object for non async redis connection/ aka Django requests
