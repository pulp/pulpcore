from rq.cli.helpers import get_redis_from_config

from pulpcore.app.settings import settings

_conn = None


def get_redis_connection():
    global _conn

    if _conn is None:
        _conn = get_redis_from_config(settings)

    return _conn
