import asyncio
from contextlib import suppress
from importlib import import_module
import logging
import os
import socket

from asgiref.sync import sync_to_async
from aiohttp import web

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "pulpcore.app.settings")
django.setup()

from django.conf import settings  # noqa: E402: module level not at top of file
from django.db.utils import (  # noqa: E402: module level not at top of file
    InterfaceError,
    OperationalError,
)

from pulpcore.app.apps import pulp_plugin_configs  # noqa: E402: module level not at top of file
from pulpcore.app.models import ContentAppStatus  # noqa: E402: module level not at top of file

from .handler import Handler  # noqa: E402: module level not at top of file
from .authentication import authenticate  # noqa: E402: module level not at top of file


log = logging.getLogger(__name__)

app = web.Application(middlewares=[authenticate])

CONTENT_MODULE_NAME = "content"


async def _heartbeat():
    name = "{pid}@{hostname}".format(pid=os.getpid(), hostname=socket.gethostname())
    heartbeat_interval = settings.CONTENT_APP_TTL // 4
    msg = "Content App '{name}' heartbeat written, sleeping for '{interarrival}' seconds".format(
        name=name, interarrival=heartbeat_interval
    )

    while True:

        try:
            content_app_status, created = await sync_to_async(
                ContentAppStatus.objects.get_or_create
            )(name=name)

            if not created:
                await sync_to_async(content_app_status.save_heartbeat)()

            log.debug(msg)
        except (InterfaceError, OperationalError):
            await sync_to_async(Handler._reset_db_connection)()
            msg = (
                "Content App '{name}' failed to write a heartbeat to the database, sleeping for "
                "'{interarrival}' seconds."
            ).format(name=name, interarrival=heartbeat_interval)
            log.info(msg)
        await asyncio.sleep(heartbeat_interval)


async def server(*args, **kwargs):
    os.chdir(settings.WORKING_DIRECTORY)

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
