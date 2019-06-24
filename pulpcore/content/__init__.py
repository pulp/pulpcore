from contextlib import suppress
from importlib import import_module

from aiohttp import web
from django.conf import settings

from pulpcore.app.apps import pulp_plugin_configs

from .handler import Handler

app = web.Application()

CONTENT_MODULE_NAME = 'content'


async def server(*args, **kwargs):
    for pulp_plugin in pulp_plugin_configs():
        if pulp_plugin.name != "pulpcore.app":
            content_module_name = '{name}.{module}'.format(name=pulp_plugin.name,
                                                           module=CONTENT_MODULE_NAME)
            with suppress(ModuleNotFoundError):
                import_module(content_module_name)
    app.add_routes([web.get(settings.CONTENT_PATH_PREFIX + '{path:.+}', Handler().stream_content)])
    return app
