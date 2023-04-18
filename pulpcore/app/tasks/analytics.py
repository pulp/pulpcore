import asyncio
import json
import logging

import aiohttp
import async_timeout

from asgiref.sync import sync_to_async
from django.conf import settings
from django.db import connection
from django.contrib.auth import get_user_model
from google.protobuf.json_format import MessageToJson

from pulpcore.app.apps import pulp_plugin_configs
from pulpcore.app.models import SystemID, Group, Domain, AccessPolicy
from pulpcore.app.models.role import Role
from pulpcore.app.models.status import ContentAppStatus
from pulpcore.app.models.task import Worker
from pulpcore.app.protobuf.analytics_pb2 import Analytics


logger = logging.getLogger(__name__)


PRODUCTION_URL = "https://analytics.pulpproject.org/"
DEV_URL = "https://dev.analytics.pulpproject.org/"


User = get_user_model()


def get_analytics_posting_url():
    """
    Return either the dev or production analytics FQDN url.

    Production version string examples:  ["3.21.1", "1.11.0"]
    Developer version string example: ["3.20.3.dev", "2.0.0a6"]

    Returns:
        The FQDN string of either the dev or production analytics site.
    """
    for app in pulp_plugin_configs():
        if not app.version.count(".") == 2:  # Only two periods allowed in prod version strings
            return DEV_URL

        x, y, z = app.version.split(".")
        for item in [x, y, z]:
            if not item.isdigit():  # Only numbers should be in the prod version string components
                return DEV_URL

    return PRODUCTION_URL


def _get_postgresql_version_string():
    return connection.cursor().connection.info.server_version


async def _postgresql_version(analytics):
    analytics.postgresql_version = await sync_to_async(_get_postgresql_version_string)()


async def _num_hosts(qs):
    hosts = set()
    async for item in qs.all():
        hosts.add(item.name.split("@")[1])
    return len(hosts)


async def _versions_data(analytics):
    for app in pulp_plugin_configs():
        new_component = analytics.components.add()
        new_component.name = app.label
        new_component.version = app.version


async def _online_content_apps_data(analytics):
    online_content_apps_qs = ContentAppStatus.objects.online()
    analytics.online_content_apps.processes = await online_content_apps_qs.acount()
    analytics.online_content_apps.hosts = await _num_hosts(online_content_apps_qs)


async def _online_workers_data(analytics):
    online_workers_qs = Worker.objects.online_workers()
    analytics.online_workers.processes = await online_workers_qs.acount()
    analytics.online_workers.hosts = await _num_hosts(online_workers_qs)


async def _system_id(analytics):
    system_id_obj = await SystemID.objects.aget()
    analytics.system_id = str(system_id_obj.pk)


async def _rbac_stats(analytics):
    analytics.rbac_stats.users = await User.objects.acount()
    analytics.rbac_stats.groups = await Group.objects.acount()
    if settings.DOMAIN_ENABLED:
        analytics.rbac_stats.domains = await Domain.objects.acount()
    else:
        analytics.rbac_stats.domains = 0
    analytics.rbac_stats.custom_access_policies = await AccessPolicy.objects.filter(
        customized=True
    ).acount()
    analytics.rbac_stats.custom_roles = await Role.objects.filter(locked=False).acount()


async def post_analytics():
    url = get_analytics_posting_url()

    analytics = Analytics()

    awaitables = (
        _system_id(analytics),
        _versions_data(analytics),
        _online_content_apps_data(analytics),
        _online_workers_data(analytics),
        _postgresql_version(analytics),
        _rbac_stats(analytics),
    )

    await asyncio.gather(*awaitables)

    try:
        async with aiohttp.ClientSession() as session:
            async with async_timeout.timeout(300):
                async with session.post(url, data=analytics.SerializeToString()) as resp:
                    if resp.status == 200:
                        logger.info(
                            ("Submitted analytics to %s. " "Information submitted includes %s"),
                            url,
                            json.loads(MessageToJson(analytics)),
                        )
                    else:
                        logger.warning(
                            "Sending analytics failed with statuscode %s from %s",
                            resp.status,
                            url,
                        )
    except asyncio.TimeoutError:
        logger.error("Timed out while sending analytics to %s", url)
    except aiohttp.ClientError as err:
        logger.error("Error sending analytics to %s: %r", url, err)
