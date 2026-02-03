import asyncio
from contextlib import suppress
from importlib import import_module
from importlib.util import find_spec
import logging
import os

from asgiref.sync import sync_to_async
from aiohttp import web
from gunicorn.arbiter import Arbiter
import django


os.environ.setdefault("DJANGO_SETTINGS_MODULE", "pulpcore.app.settings")
django.setup()

from django.conf import settings  # noqa: E402: module level not at top of file
from django.db.utils import (  # noqa: E402: module level not at top of file
    IntegrityError,
    InterfaceError,
    DatabaseError,
)

from pulpcore.app.apps import pulp_plugin_configs  # noqa: E402: module level not at top of file
from pulpcore.app.models import AppStatus  # noqa: E402: module level not at top of file
from pulpcore.app.util import get_worker_name  # noqa: E402: module level not at top of file

from .handler import Handler  # noqa: E402: module level not at top of file
from .authentication import authenticate, guid  # noqa: E402: module level not at top of file


log = logging.getLogger(__name__)

if settings.OTEL_ENABLED:
    from .instrumentation import instrumentation  # noqa: E402: module level not at top of file

    app = web.Application(middlewares=[guid, authenticate, instrumentation()])
else:
    app = web.Application(middlewares=[guid, authenticate])


if settings.UVLOOP_ENABLED:
    if not find_spec("uvloop"):
        raise RuntimeError("The library 'uvloop' must be installed if UVLOOP_ENABLED is true.")
    log.info("Using uvloop as the asyncio event loop.")


CONTENT_MODULE_NAME = "content"


async def _heartbeat():
    name = get_worker_name()
    heartbeat_interval = settings.CONTENT_APP_TTL // 4
    msg = "Content App '{name}' heartbeat written, sleeping for '{interarrival}' seconds".format(
        name=name, interarrival=heartbeat_interval
    )
    fail_msg = ("Content App '{name}' failed to write a heartbeat to the database.").format(
        name=name
    )
    versions = {app.label: app.version for app in pulp_plugin_configs()}

    try:
        app_status = await AppStatus.objects.acreate(
            name=name, app_type="content", versions=versions
        )
    except IntegrityError:
        log.error(f"A content app with name {name} already exists in the database.")
        exit(Arbiter.WORKER_BOOT_ERROR)
    try:
        while True:
            await asyncio.sleep(heartbeat_interval)
            try:
                await app_status.asave_heartbeat()
                log.debug(msg)
            except (InterfaceError, DatabaseError):
                await sync_to_async(Handler._reset_db_connection)()
                try:
                    await app_status.asave_heartbeat()
                    log.debug(msg)
                except (InterfaceError, DatabaseError) as e:
                    log.error(f"{fail_msg} Exception: {str(e)}")
                    exit(Arbiter.WORKER_BOOT_ERROR)
    finally:
        if app_status:
            await app_status.adelete()


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
