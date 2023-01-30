"""Utilities for Pulpcore tests."""
import aiohttp
import asyncio
from dataclasses import dataclass


async def get_response(url):
    async with aiohttp.ClientSession() as session:
        return await session.get(url)


SLEEP_TIME = 0.3


try:
    from pulp_smash.pulp3.bindings import PulpTaskError, PulpTaskGroupError
except ImportError:

    class PulpTaskError(Exception):
        """Exception to describe task errors."""

        def __init__(self, task):
            """Provide task info to exception."""
            description = task.to_dict()["error"].get("description")
            super().__init__(self, f"Pulp task failed ({description})")
            self.task = task

    class PulpTaskGroupError(Exception):
        """Exception to describe task group errors."""

        def __init__(self, task_group):
            """Provide task info to exception."""
            super().__init__(self, f"Pulp task group failed ({task_group})")
            self.task_group = task_group


@dataclass
class MockDownload:
    """Class for representing a downloaded file."""

    body: bytes
    response_obj: aiohttp.ClientResponse

    def __init__(self, body, response_obj):
        self.body = body
        self.response_obj = response_obj


def download_file(url, auth=None, headers=None):
    """Download a file.

    :param url: str URL to the file to download
    :param auth: `aiohttp.BasicAuth` containing basic auth credentials
    :param headers: dict of headers to send with the GET request
    :return: Download
    """
    return asyncio.run(_download_file(url, auth=auth, headers=headers))


async def _download_file(url, auth=None, headers=None):
    async with aiohttp.ClientSession(auth=auth, raise_for_status=True) as session:
        async with session.get(url, ssl=False, headers=headers) as response:
            return MockDownload(body=await response.read(), response_obj=response)
