import redis as redis_module
from django.conf import settings
from redis import Redis
from redis.asyncio import Redis as aRedis

_conn = None
_a_conn = None

# redis-py 8.0.0 changed default retries from 3 to 10, causing content app request timeouts when
# Redis is unreachable. This reverts only retries; backoff base/cap are kept at 8.0.0 defaults.
_CONNECTION_KWARGS = {}
if redis_module.VERSION >= (8,):
    from redis.backoff import ExponentialWithJitterBackoff
    from redis.retry import Retry

    _CONNECTION_KWARGS["retry"] = Retry(
        backoff=ExponentialWithJitterBackoff(base=0.01, cap=1), retries=3
    )


def _redis_is_needed():
    return (
        getattr(settings, "CACHE_ENABLED", None)
        or getattr(settings, "WORKER_TYPE", None) == "redis"
    )


def _get_connection_from_class(redis_class):
    if not _redis_is_needed():
        return None
    redis_url = getattr(settings, "REDIS_URL", None)
    if redis_url is not None:
        return redis_class.from_url(redis_url, **_CONNECTION_KWARGS)
    else:
        return redis_class(
            host=settings.REDIS_HOST,
            port=settings.REDIS_PORT,
            db=settings.REDIS_DB,
            password=settings.REDIS_PASSWORD,
            ssl=settings.REDIS_SSL,
            ssl_ca_certs=settings.REDIS_SSL_CA_CERTS,
            **_CONNECTION_KWARGS,
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
