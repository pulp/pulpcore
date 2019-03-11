import sys
from pulpcore.app.settings import settings


settings.configure()

rq_settings = ['REDIS_URL', 'REDIS_HOST', 'REDIS_PORT', 'REDIS_DB', 'REDIS_PASSWORD', 'SENTINEL']

for s in rq_settings:
    value = settings.get(s, None)
    if value:
        setattr(sys.modules[__name__], s, value)
