"""Utilities for Pulpcore tests."""

import hashlib
import os

import requests

from aiohttp import web
from dataclasses import dataclass
from multidict import CIMultiDict


SLEEP_TIME = 0.5
TASK_TIMEOUT = 30 * 60  # 30 minutes


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


class BindingsNamespace:
    def __init__(self, module, client):
        self.module = module
        self.client = client
        self.ApiException = self.module.exceptions.ApiException

    def __getattr__(self, name):
        # __getattr__ is only consulted if nothing is found in __dict__.
        assert name.endswith("Api")

        api_object = getattr(self.module, name)(self.client)
        self.__dict__[name] = api_object
        return api_object


@dataclass
class MockDownload:
    """Class for representing a downloaded file."""

    body: bytes
    response_obj: requests.Response

    def __init__(self, body, response_obj):
        self.body = body
        self.response_obj = response_obj


def add_recording_route(app, fixtures_root):
    requests = []

    async def all_requests_handler(request):
        requests.append(request)
        path = fixtures_root / request.raw_path[1:]  # Strip off leading '/'
        if path.is_file():
            return web.FileResponse(
                path, headers=CIMultiDict({"content-type": "application/octet-stream"})
            )
        else:
            raise web.HTTPNotFound()

    app.add_routes([web.get("/{tail:.*}", all_requests_handler)])

    return requests


def download_file(url, auth=None, headers=None):
    """Download a file.

    :param url: str URL to the file to download
    :param auth: `requests.auth.HTTPBasicAuth` containing basic auth credentials
    :param headers: dict of headers to send with the GET request
    :return: Download
    """
    response = requests.get(url, auth=auth, headers=headers, verify=False)
    return MockDownload(body=response.content, response_obj=response)


def generate_iso(full_path, size=1024, relative_path=None):
    """Generate a random file."""
    with open(full_path, "wb") as fout:
        contents = os.urandom(size)
        fout.write(contents)
        fout.flush()
    digest = hashlib.sha256(contents).hexdigest()
    if relative_path:
        name = relative_path
    else:
        name = full_path.name
    return {"name": name, "size": size, "digest": digest}


def generate_manifest(name, file_list):
    """Generate a pulp_file manifest file for a list of files."""
    with open(name, "wt") as fout:
        for file in file_list:
            fout.write("{},{},{}\n".format(file["name"], file["digest"], file["size"]))
        fout.flush()
    return name


def get_files_in_manifest(url):
    """
    Download a File Repository manifest and return content as a list of tuples.
    [(name,sha256,size),]
    """
    files = set()
    r = download_file(url)
    for line in r.body.splitlines():
        files.add(tuple(line.decode().split(",")))
    return files


def get_from_url(url, auth=None, headers=None):
    """
    Performs a GET request on a URL and returns a requests.Response object.
    """
    return requests.get(url, auth=auth, headers=headers, verify=False)
