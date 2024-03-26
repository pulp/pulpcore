from redis import Redis
from redis.asyncio import Redis as aRedis

from pulpcore.app.settings import settings

_conn = None
_a_conn = None


def _get_connection_from_class(redis_class):
    if not settings.get("CACHE_ENABLED"):
        return None
    redis_url = settings.get("REDIS_URL")
    if redis_url is not None:
        return redis_class.from_url(redis_url)
    else:
        return redis_class(
            host=settings.REDIS_HOST,
            port=settings.REDIS_PORT,
            db=settings.REDIS_DB,
            password=settings.REDIS_PASSWORD,
            ssl=settings.REDIS_SSL,
            ssl_ca_certs=settings.REDIS_SSL_CA_CERTS,
        )


def get_redis_connection():
    global _conn

    if _conn is None:
        _conn = _get_connection_from_class(Redis)

    return _conn


def get_async_redis_connection():
    global _a_conn

    if _a_conn is None:
        _a_conn = _get_connection_from_class(aRedis)

    return _a_conn
