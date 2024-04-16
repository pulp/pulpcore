import asyncio
from contextlib import suppress
from importlib import import_module
import logging
import os
import socket

from asgiref.sync import sync_to_async
from aiohttp import web

from .instrumentation import middleware as instrumentation

import django


os.environ.setdefault("DJANGO_SETTINGS_MODULE", "pulpcore.app.settings")
django.setup()

from django.conf import settings  # noqa: E402: module level not at top of file
from django.db.utils import (  # noqa: E402: module level not at top of file
    InterfaceError,
    DatabaseError,
)

from pulpcore.app.apps import pulp_plugin_configs  # noqa: E402: module level not at top of file
from pulpcore.app.models import ContentAppStatus  # noqa: E402: module level not at top of file

from .handler import Handler  # noqa: E402: module level not at top of file
from .authentication import authenticate  # noqa: E402: module level not at top of file


log = logging.getLogger(__name__)

app = web.Application(middlewares=[authenticate, instrumentation])

CONTENT_MODULE_NAME = "content"


async def _heartbeat():
    content_app_status = None
    name = "{pid}@{hostname}".format(pid=os.getpid(), hostname=socket.gethostname())
    heartbeat_interval = settings.CONTENT_APP_TTL // 4
    msg = "Content App '{name}' heartbeat written, sleeping for '{interarrival}' seconds".format(
        name=name, interarrival=heartbeat_interval
    )
    fail_msg = (
        "Content App '{name}' failed to write a heartbeat to the database, sleeping for "
        "'{interarrival}' seconds."
    ).format(name=name, interarrival=heartbeat_interval)
    versions = {app.label: app.version for app in pulp_plugin_configs()}

    try:
        while True:
            try:
                content_app_status, created = await ContentAppStatus.objects.aget_or_create(
                    name=name, defaults={"versions": versions}
                )

                if not created:
                    await sync_to_async(content_app_status.save_heartbeat)()

                    if content_app_status.versions != versions:
                        content_app_status.versions = versions
                        await content_app_status.asave(update_fields=["versions"])

                log.debug(msg)
            except (InterfaceError, DatabaseError):
                await sync_to_async(Handler._reset_db_connection)()
                log.info(fail_msg)
            await asyncio.sleep(heartbeat_interval)
    finally:
        if content_app_status:
            await content_app_status.adelete()


async def _heartbeat_ctx(app):
    heartbeat_task = asyncio.create_task(_heartbeat())
    yield
    heartbeat_task.cancel()
    try:
        await heartbeat_task
    except asyncio.CancelledError:
        pass


async def server(*args, **kwargs):
    os.chdir(settings.WORKING_DIRECTORY)

    for pulp_plugin in pulp_plugin_configs():
        if pulp_plugin.name != "pulpcore.app":
            content_module_name = "{name}.{module}".format(
                name=pulp_plugin.name, module=CONTENT_MODULE_NAME
            )
            with suppress(ModuleNotFoundError):
                import_module(content_module_name)
    path_prefix = settings.CONTENT_PATH_PREFIX
    if settings.DOMAIN_ENABLED:
        path_prefix = path_prefix + "{pulp_domain}/"
        app.add_routes([web.get(path_prefix[:-1], Handler().list_distributions)])
    app.add_routes([web.get(path_prefix, Handler().list_distributions)])
    app.add_routes([web.get(path_prefix + "{path:.+}", Handler().stream_content)])
    app.cleanup_ctx.append(_heartbeat_ctx)
    return app
