import asyncio
import json
import logging

import aiohttp
import async_timeout

from asgiref.sync import sync_to_async
from google.protobuf.json_format import MessageToJson

from pulpcore.app.apps import pulp_plugin_configs
from pulpcore.app.util import get_telemetry_posting_url
from pulpcore.app.models import SystemID
from pulpcore.app.models.status import ContentAppStatus
from pulpcore.app.models.task import Worker
from pulpcore.app.protobuf.telemetry_pb2 import Telemetry


logger = logging.getLogger(__name__)


async def _num_hosts(qs):
    hosts = set()
    items = await sync_to_async(list)(qs.all())
    for item in items:
        hosts.add(item.name.split("@")[1])
    return len(hosts)


async def _versions_data(telemetry):
    for app in pulp_plugin_configs():
        new_component = telemetry.components.add()
        new_component.name = app.label
        new_component.version = app.version


async def _online_content_apps_data(telemetry):
    online_content_apps_qs = ContentAppStatus.objects.online()
    telemetry.online_content_apps.processes = await sync_to_async(online_content_apps_qs.count)()
    telemetry.online_content_apps.hosts = await _num_hosts(online_content_apps_qs)


async def _online_workers_data(telemetry):
    online_workers_qs = Worker.objects.online_workers()
    telemetry.online_workers.processes = await sync_to_async(online_workers_qs.count)()
    telemetry.online_workers.hosts = await _num_hosts(online_workers_qs)


async def _system_id(telemetry):
    system_id_obj = await sync_to_async(SystemID.objects.get)()
    telemetry.system_id = str(system_id_obj.pk)


async def post_telemetry():
    url = get_telemetry_posting_url()

    telemetry = Telemetry()

    awaitables = (
        _system_id(telemetry),
        _versions_data(telemetry),
        _online_content_apps_data(telemetry),
        _online_workers_data(telemetry),
    )

    await asyncio.gather(*awaitables)

    try:
        async with aiohttp.ClientSession() as session:
            async with async_timeout.timeout(300):
                async with session.post(url, data=telemetry.SerializeToString()) as resp:
                    if resp.status == 200:
                        logger.info(
                            ("Submitted telemetry to %s. " "Information submitted includes %s"),
                            url,
                            json.loads(MessageToJson(telemetry)),
                        )
                    else:
                        logger.warning(
                            "Sending telemetry failed with statuscode %s from %s",
                            resp.status,
                            url,
                        )
    except asyncio.TimeoutError:
        logger.error("Timed out while sending telemetry to %s", url)
    except aiohttp.ClientError as err:
        logger.error("Error sending telemetry to %s: %r", url, err)
