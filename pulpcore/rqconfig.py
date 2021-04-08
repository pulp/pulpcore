import sys

from pulpcore.app.settings import settings

rq_settings = [
    "REDIS_URL",
    "REDIS_HOST",
    "REDIS_PORT",
    "REDIS_DB",
    "REDIS_PASSWORD",
    "REDIS_SSL",
    "SENTINEL",
]

settings.populate_obj(sys.modules[__name__], keys=rq_settings)
