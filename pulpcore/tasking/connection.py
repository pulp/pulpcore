from pulpcore.app.settings import settings
from rq.cli.helpers import get_redis_from_config

_conn = None


def get_redis_connection():
    global _conn

    if _conn is None:
        _conn = get_redis_from_config(settings)

    return _conn
