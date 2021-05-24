from aioredis import Redis as aRedis
from rq.cli.helpers import get_redis_from_config

from pulpcore.app.settings import settings

_conn = None
_a_conn = None


def get_redis_connection():
    global _conn

    if _conn is None:
        _conn = get_redis_from_config(settings)

    return _conn


def get_async_redis_connection():
    global _a_conn

    if _a_conn is None:
        _a_conn = get_redis_from_config(settings, aRedis)

    return _a_conn
