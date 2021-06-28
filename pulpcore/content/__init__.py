import asyncio
from contextlib import suppress
from gettext import gettext as _
from importlib import import_module
import logging
import os
import socket

from aiohttp import web

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "pulpcore.app.settings")
# Until Django supports async ORM natively this is the best we can do given these parts of Pulp
# run in coroutines. We try to ensure it is safe by never passing ORM data between co-routines.
os.environ.setdefault("DJANGO_ALLOW_ASYNC_UNSAFE", "true")

django.setup()

from django.conf import settings  # noqa: E402: module level not at top of file

from pulpcore.app.apps import pulp_plugin_configs  # noqa: E402: module level not at top of file
from pulpcore.app.models import ContentAppStatus  # noqa: E402: module level not at top of file

from .handler import Handler, loop  # noqa: E402: module level not at top of file


log = logging.getLogger(__name__)

app = web.Application()

CONTENT_MODULE_NAME = "content"


async def _heartbeat():
    name = "{pid}@{hostname}".format(pid=os.getpid(), hostname=socket.gethostname())
    heartbeat_interval = settings.CONTENT_APP_TTL // 4
    i8ln_msg = _("Content App '{name}' heartbeat written, sleeping for '{interarrival}' seconds")
    msg = i8ln_msg.format(name=name, interarrival=heartbeat_interval)

    def get_status_blocking():
        return ContentAppStatus.objects.get_or_create(name=name)

    while True:
        content_app_status, created = await loop.run_in_executor(None, get_status_blocking)

        def save_heartbeat_blocking():
            content_app_status.save_heartbeat()

        if not created:
            await loop.run_in_executor(None, save_heartbeat_blocking)

        log.debug(msg)
        await asyncio.sleep(heartbeat_interval)


async def server(*args, **kwargs):
    asyncio.ensure_future(_heartbeat())
    for pulp_plugin in pulp_plugin_configs():
        if pulp_plugin.name != "pulpcore.app":
            content_module_name = "{name}.{module}".format(
                name=pulp_plugin.name, module=CONTENT_MODULE_NAME
            )
            with suppress(ModuleNotFoundError):
                import_module(content_module_name)
    app.add_routes([web.get(settings.CONTENT_PATH_PREFIX, Handler().list_distributions)])
    app.add_routes([web.get(settings.CONTENT_PATH_PREFIX + "{path:.+}", Handler().stream_content)])
    return app
