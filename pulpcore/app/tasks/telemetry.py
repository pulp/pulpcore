import asyncio
import logging

import aiohttp
import async_timeout

from asgiref.sync import sync_to_async

from pulpcore.app.apps import pulp_plugin_configs
from pulpcore.app.models import SystemID
from pulpcore.app.models.status import ContentAppStatus
from pulpcore.app.models.task import Worker


logger = logging.getLogger(__name__)


PRODUCTION_URL = "https://analytics-pulpproject-org.pulpproject.workers.dev/"
DEV_URL = "https://dev-analytics-pulpproject-org.pulpproject.workers.dev/"


async def _num_hosts(qs):
    hosts = set()
    items = await sync_to_async(list)(qs.all())
    for item in items:
        hosts.add(item.name.split("@")[1])
    return len(hosts)


async def _versions_data():
    versions = []

    for app in pulp_plugin_configs():
        versions.append({"component": app.label, "version": app.version})

    return {"versions": versions}


async def _online_content_apps_data():
    online_content_apps = ContentAppStatus.objects.online()
    online_content_apps_processes = await sync_to_async(online_content_apps.count)()
    online_content_apps_hosts = await _num_hosts(online_content_apps)

    return {
        "online_content_apps": {
            "processes": online_content_apps_processes,
            "hosts": online_content_apps_hosts,
        },
    }


async def _online_workers_data():
    online_workers = Worker.objects.online_workers()
    online_workers_processes = await sync_to_async(online_workers.count)()
    online_workers_hosts = await _num_hosts(online_workers)

    return {
        "online_workers": {
            "processes": online_workers_processes,
            "hosts": online_workers_hosts,
        },
    }


async def _system_id():
    system_id_entry = await sync_to_async(SystemID.objects.get)()
    return {"system_id": str(system_id_entry.pk)}


def _get_posting_url():
    for app in pulp_plugin_configs():
        if ".dev" in app.version:
            return DEV_URL

    return PRODUCTION_URL


async def post_telemetry():
    url = _get_posting_url()

    if url == PRODUCTION_URL:
        return  # Initially only dev systems receive posted data. If we got here, bail.

    data = {}

    awaitables = (
        _system_id(),
        _versions_data(),
        _online_content_apps_data(),
        _online_workers_data(),
    )

    data_iterable_to_merge = await asyncio.gather(*awaitables)
    for data_to_merge in data_iterable_to_merge:
        data.update(data_to_merge)

    try:
        async with aiohttp.ClientSession() as session:
            async with async_timeout.timeout(30):
                async with session.post(url, json=data) as resp:
                    if resp.status == 200:
                        logger.info(
                            ("Submitted telemetry to %s. " "Information submitted includes %s"),
                            url,
                            data,
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
