import enum
import json
import time

from functools import wraps

from django.http import HttpResponseRedirect, HttpResponse, FileResponse as ApiFileResponse

from rest_framework.request import Request as ApiRequest

from aiohttp.web import FileResponse, Response, HTTPSuccessful, Request, StreamResponse
from aiohttp.web_exceptions import HTTPFound

from redis import ConnectionError
from redis.asyncio import ConnectionError as AConnectionError

from pulpcore.app.settings import settings
from pulpcore.app.redis_connection import (
    get_redis_connection,
    get_async_redis_connection,
)
from pulpcore.responses import ArtifactResponse

from pulpcore.metrics import artifacts_size_counter

DEFAULT_EXPIRES_TTL = settings.CACHE_SETTINGS["EXPIRES_TTL"]


class CacheKeys(enum.Enum):
    """Available keys to construct the index key for cache entry."""

    path = "path"
    host = "host"
    method = "method"


def connection_error_wrapper(func):
    """A decorator that enables sync functions which use Redis to swallow connection errors."""

    @wraps(func)
    def wrapper(*args, **kwargs):
        """Handle connection errors, specific to the sync context, raised by the Redis client."""
        try:
            return func(*args, **kwargs)
        except (ConnectionError, TypeError):
            # TypeError is raised when an invalid port number for the Redis connection is configured
            return None

    return wrapper


def aconnection_error_wrapper(func):
    """A decorator that enables async functions which use Redis to swallow connection errors."""

    @wraps(func)
    async def wrapper(*args, **kwargs):
        """Handle connection errors, specific to the async context, raised by the Redis client."""
        try:
            return await func(*args, **kwargs)
        except (AConnectionError, TypeError):
            # TypeError is raised when an invalid port number for the Redis connection is configured
            return None

    return wrapper


class Cache:
    """Base class for Pulp's cache"""

    default_base_key = "PULP_CACHE"
    default_expires_ttl = DEFAULT_EXPIRES_TTL

    def __init__(self):
        """Creates synchronous cache instance"""
        self.redis = get_redis_connection()

    @connection_error_wrapper
    def get(self, key, base_key=None):
        """Gets cached entry of key"""
        base_key = base_key or self.default_base_key
        if key is None:
            return self.redis.hgetall(base_key)
        return self.redis.hget(base_key, key)

    @connection_error_wrapper
    def set(self, key, value, expires=None, base_key=None):
        """Sets the cached entry at key"""
        base_key = base_key or self.default_base_key
        ret = self.redis.hset(base_key, key, value)
        if expires:
            self.redis.expire(base_key, expires)
        return ret

    @connection_error_wrapper
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

    @connection_error_wrapper
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


class SyncContentCache(Cache):
    """Cache object meant to be used within the synchronous context."""

    RESPONSE_TYPES = {
        "FileResponse": ApiFileResponse,
        "Response": HttpResponse,
        "Redirect": HttpResponseRedirect,
    }

    def __init__(self, base_key=None, expires_ttl=None, keys=None, auth=None):
        """
        Initiates a cache instance to be used for dealing with a django server.

        Args:
            base_key: a string to group entries under, defaults to DEFAULT_BASE_KEY,
                      can be a callable taking the request and cache instance as arguments
            expires_ttl: length in seconds entries should live in the cache, EXPIRES_TTL is default
            keys: a list of CacheKeys to use for key creation upon entry placement,
                (path, method) is default
            auth: a callable to check authorization of the request; takes the request, cache
                  instance, and base_key as arguments.
        """
        super().__init__()
        self.default_base_key = base_key or self.default_base_key
        self.keys = keys or (
            CacheKeys.path,
            CacheKeys.method,
        )
        self.default_expires_ttl = expires_ttl or self.default_expires_ttl
        self.auth = auth

    def __call__(self, func):
        """A decorator to make the handler cached."""
        if not settings.CACHE_ENABLED:
            return func

        def cached_function(*args, **kwargs):
            request = self.get_request_from_args(args)
            bk = self.default_base_key
            if callable(self.default_base_key):
                bk = self.default_base_key(request, self)
            if self.auth:
                self.auth(request, self, bk)
            key = self.make_key(request)
            # Check cache
            response = self.make_response(key, bk)
            if response is None:
                # Cache miss, create new entry
                response = self.make_entry(key, bk, func, args, kwargs, self.default_expires_ttl)
            return response

        return cached_function

    def get_request_from_args(self, args):
        """Finds the request object from list of args"""
        for arg in args:
            if isinstance(arg, ApiRequest):
                return arg

    def make_response(self, key, base_key):
        """Tries to find the cached entry and turn it into a proper response"""
        entry = self.get(key, base_key)
        if not entry:
            return None
        entry = json.loads(entry)
        response_type = entry.pop("type", None)
        # None means "doesn't expire", unset means "already expired".
        expires = entry.pop("expires", -1)
        if (not response_type or response_type not in self.RESPONSE_TYPES) or (
            expires and expires < time.time()
        ):
            # Bad entry, delete from cache
            self.delete(key, base_key)
            return None

        response = self.RESPONSE_TYPES[response_type](**entry)
        response.headers["X-PULP-CACHE"] = "HIT"
        return response

    def make_entry(self, key, base_key, handler, args, kwargs, expires=DEFAULT_EXPIRES_TTL):
        """Gets the response for the request and try to turn it into a cacheable entry"""
        response = handler(*args, **kwargs)
        entry = {"headers": dict(response.headers), "status": response.status_code}
        if expires is not None:
            # Redis TTL is not sufficient: https://github.com/pulp/pulpcore/issues/4845
            entry["expires"] = expires + time.time()
        else:
            # Settings allow you to set None to mean "does not expire". Persist.
            entry["expires"] = None
        response.headers["X-PULP-CACHE"] = "MISS"
        if isinstance(response, HttpResponseRedirect):
            entry["redirect_to"] = str(response.headers["Location"])
            entry["type"] = "Redirect"
        elif isinstance(response, ApiFileResponse):
            entry["path"] = str(response.filename)
            entry["type"] = "FileResponse"
        elif isinstance(response, HttpResponse):
            entry["content"] = response.content.decode("utf-8")
            entry["type"] = "Response"
        else:
            # We don't cache StreamResponses or errors
            return response

        # TODO look into smaller format, maybe some compression on the text
        self.set(key, json.dumps(entry), expires, base_key=base_key)
        return response

    def make_key(self, request):
        """Makes the key based off the request"""
        all_keys = {
            CacheKeys.path: request.path,
            CacheKeys.method: request.method,
            # TODO: this may fail when the host is behind multiple proxies
            # https://docs.djangoproject.com/en/3.2/ref/request-response/
            CacheKeys.host: request.get_host(),
        }
        key = ":".join(all_keys[k] for k in self.keys)
        return key


class AsyncCache:
    """Base class for asynchronous Pulp Cache"""

    default_base_key = "PULP_CACHE"
    default_expires_ttl = DEFAULT_EXPIRES_TTL

    def __init__(self):
        """Creates asynchronous cache instance"""
        self.redis = get_async_redis_connection()

    @aconnection_error_wrapper
    async def get(self, key, base_key=None):
        """Gets cached entry of key"""
        base_key = base_key or self.default_base_key
        if key is None:
            return await self.redis.hgetall(base_key)
        return await self.redis.hget(base_key, key)

    @aconnection_error_wrapper
    async def set(self, key, value, expires=None, base_key=None):
        """Sets the cached entry at key"""
        base_key = base_key or self.default_base_key
        ret = await self.redis.hset(base_key, key, value)
        if expires:
            await self.redis.expire(base_key, expires)
        return ret

    @aconnection_error_wrapper
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

    @aconnection_error_wrapper
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


class AsyncContentCache(AsyncCache):
    """Cache object meant to be used for the content app"""

    RESPONSE_TYPES = {
        "FileResponse": FileResponse,
        "ArtifactResponse": ArtifactResponse,
        "Response": Response,
        "Redirect": HTTPFound,
    }

    ADD_TRAILING_SLASH = True

    def __init__(self, base_key=None, expires_ttl=None, keys=None, auth=None):
        """
        Initiates a cache instance to be used for dealing with an aiohttp server

        Args:
            base_key: a string to group entries under, defaults to DEFAULT_BASE_KEY,
                      can be a callable taking the request and cache instance as arguments
            expires_ttl: length in seconds entries should live in the cache, EXPIRES_TTL is default
            keys: a list of CacheKeys to use for key creation upon entry placement,
                (path, method) is default
            auth: a callable to check authorization of the request; takes the request, cache
                  instance, and base_key as arguments.
        """
        super().__init__()
        self.default_base_key = base_key or self.default_base_key
        self.keys = keys or (
            CacheKeys.path,
            CacheKeys.method,
        )
        self.default_expires_ttl = expires_ttl or self.default_expires_ttl
        self.auth = auth

    def __call__(self, func):
        """Decorator magic call to make the handler cached"""
        if not settings.CACHE_ENABLED:
            return func

        async def cached_function(*args, **kwargs):
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
                response = await self.make_entry(
                    key, bk, func, args, kwargs, self.default_expires_ttl
                )
            elif size := response.headers.get("X-PULP-ARTIFACT-SIZE"):
                artifacts_size_counter.add(size)

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

        if binary := entry.pop("body", None):
            # raw binary data were translated to their hexadecimal representation and saved in
            # the cache as a regular string; now, it is necessary to translate the data back
            # to its original representation that will be returned in the HTTP response BODY:
            # https://docs.aiohttp.org/en/stable/web_reference.html#response
            entry["body"] = bytes.fromhex(binary)

        response_type = entry.pop("type", None)
        # None means "doesn't expire", unset means "already expired".
        expires = entry.pop("expires", -1)
        if (not response_type or response_type not in self.RESPONSE_TYPES) or (
            expires and expires < time.time()
        ):
            # Bad entry, delete from cache
            await self.delete(key, base_key)
            return None
        response = self.RESPONSE_TYPES[response_type](**entry)
        response.headers.update({"X-PULP-CACHE": "HIT"})
        return response

    async def make_entry(self, key, base_key, handler, args, kwargs, expires=DEFAULT_EXPIRES_TTL):
        """Gets the response for the request and try to turn it into a cacheable entry"""
        try:
            response = await handler(*args, **kwargs)
        except (HTTPSuccessful, HTTPFound) as e:
            response = e

        original_response = response
        if isinstance(response, StreamResponse):
            if hasattr(response, "future_response"):
                response = response.future_response

        entry = {"headers": dict(response.headers), "status": response.status}
        if expires is not None:
            # Redis TTL is not sufficient: https://github.com/pulp/pulpcore/issues/4845
            entry["expires"] = expires + time.time()
        else:
            # Settings allow you to set None to mean "does not expire". Persist.
            entry["expires"] = None
        response.headers.update({"X-PULP-CACHE": "MISS"})
        if isinstance(response, FileResponse):
            entry["path"] = str(response._path)
            entry["type"] = "FileResponse"
        elif isinstance(response, ArtifactResponse):
            entry["artifact_pk"] = str(response._artifact.pk)
            entry["type"] = "ArtifactResponse"
        elif isinstance(response, (Response, HTTPSuccessful)):
            body = response.body
            if isinstance(body, bytes):
                # convert bytes into a json dump-able string
                entry["body"] = body.hex()
            else:
                entry["text"] = getattr(body, "_value", body).decode("utf-8")
            entry["type"] = "Response"
        elif isinstance(response, HTTPFound):
            entry["location"] = str(response.location)
            entry["type"] = "Redirect"
        else:
            # We don't cache errors
            return response

        # TODO look into smaller format, maybe some compression on the text
        await self.set(key, json.dumps(entry), expires, base_key=base_key)
        return original_response

    def make_key(self, request):
        """Makes the key based off the request"""
        # Might potentially have to make this async if keys require async data from request
        all_keys = {
            CacheKeys.path: request.path,
            CacheKeys.method: request.method,
            CacheKeys.host: request.url.host,
        }
        key = ":".join(all_keys[k] for k in self.keys)
        return key
