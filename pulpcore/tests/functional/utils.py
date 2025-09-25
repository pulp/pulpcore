"""Utilities for Pulpcore tests."""

import aiohttp
import asyncio
import hashlib
import os
import random
import traceback
import sys
import multiprocessing as mp

from multiprocessing.connection import Connection
from functools import partial
from contextlib import contextmanager
from typing import NamedTuple
from aiohttp import web
from dataclasses import dataclass
from multidict import CIMultiDict


async def get_response(url):
    async with aiohttp.ClientSession() as session:
        return await session.get(url)


SLEEP_TIME = 0.5
TASK_TIMEOUT = 30 * 60  # 30 minutes


try:
    from pulp_smash.pulp3.bindings import PulpTaskError, PulpTaskGroupError
except ImportError:

    class PulpTaskError(Exception):
        """Exception to describe task errors."""

        def __init__(self, task):
            """Provide task info to exception."""
            description = task.to_dict()
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
        # So we get memoization for free.
        if name.endswith("Api"):
            api_object = getattr(self.module, name)(self.client)
        else:
            api_object = getattr(self.module, name)
        self.__dict__[name] = api_object
        return api_object


@dataclass
class MockDownload:
    """Class for representing a downloaded file."""

    body: bytes
    response_obj: aiohttp.ClientResponse

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
    :param auth: `aiohttp.BasicAuth` containing basic auth credentials
    :param headers: dict of headers to send with the GET request
    :return: Download
    """
    return asyncio.run(_download_file(url, auth=auth, headers=headers))


async def _download_file(url, auth=None, headers=None):
    async with aiohttp.ClientSession(auth=auth, raise_for_status=True) as session:
        async with session.get(url, ssl=False, headers=headers) as response:
            return MockDownload(body=await response.read(), response_obj=response)


def generate_iso(full_path, size=1024, relative_path=None, seed=None):
    """Generate a random file."""
    with open(full_path, "wb") as fout:
        if seed:
            random.seed(seed)
            contents = random.randbytes(size)
        else:
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
    Performs a GET request on a URL and returns an aiohttp.Response object.
    """
    return asyncio.run(_get_from_url(url, auth=auth, headers=headers))


async def _get_from_url(url, auth=None, headers=None):
    async with aiohttp.ClientSession(auth=auth) as session:
        async with session.get(url, ssl=False, headers=headers) as response:
            return response


class ProcessErrorData(NamedTuple):
    error: Exception
    stacktrace: str


class IpcUtil:
    TIMEOUT_ERROR_MESSAGE = (
        "Tip: make sure the last 'with turn()' (in execution order) "
        "is called with 'actor_turn(done=True)', otherwise it may hang."
    )
    SUBPROCESS_ERROR_HEADER_TEMPLATE = "Error from sub-process (pid={pid}) on test using IpcUtil"
    TURN_WAIT_TIMEOUT = 1

    @staticmethod
    def run(host_act, child_act) -> list:
        """Run two processes in synchronous alternate turns.

        The act are functions with the signature (act_turn, log), where act_turn is
        a context manager where each step of the act takes place, and log is a
        queue where each actor can put messages in using Q.put(item).

        Args:
            host_act: The function of the act that start the communication
            child_act: The function of the act that follows host_act
        Returns:
            A list with the items collected via log.
        """
        conn_1, conn_2 = mp.Pipe()
        log = mp.SimpleQueue()
        lock = mp.Lock()
        turn_1 = partial(IpcUtil._actor_turn, conn_1, starts=True, log=log, lock=lock)
        turn_2 = partial(IpcUtil._actor_turn, conn_2, starts=False, log=log, lock=lock)
        proc_1 = mp.Process(target=host_act, args=(turn_1, log))
        proc_2 = mp.Process(target=child_act, args=(turn_2, log))
        proc_1.start()
        proc_2.start()
        try:
            proc_1.join()
        finally:
            conn_1.send("1")
        try:
            proc_2.join()
        finally:
            conn_2.send("1")
        conn_1.close()
        conn_2.close()
        result = IpcUtil.read_log(log)
        log.close()
        if proc_1.exitcode != 0 or proc_2.exitcode != 0:
            error = Exception("General exception")
            stacktrace = "No stacktrace"
            for item in result:
                if isinstance(item, ProcessErrorData):
                    error, stacktrace = item
                    break
            raise Exception(stacktrace) from error
        return result

    @staticmethod
    @contextmanager
    def _actor_turn(conn: Connection, starts: bool, log, lock: mp.Lock, done: bool = False):
        def flush_conn(conn: Connection):
            if not conn.poll(IpcUtil.TURN_WAIT_TIMEOUT):
                raise TimeoutError(IpcUtil.TIMEOUT_ERROR_MESSAGE)
            conn.recv()

        try:
            if starts:
                with lock:
                    conn.send("done")
                    yield
                if not done:
                    flush_conn(conn)
            else:
                flush_conn(conn)
                with lock:
                    yield
                    conn.send("done")
        except Exception as e:
            traceback.print_exc(file=sys.stderr)
            error_header = IpcUtil.SUBPROCESS_ERROR_HEADER_TEMPLATE.format(pid=os.getpid())
            traceback_str = f"{error_header}\n\n{traceback.format_exc()}"
            error = ProcessErrorData(e, traceback_str)
            log.put(error)
            exit(1)

    @staticmethod
    def read_log(log: mp.SimpleQueue) -> list:
        result = []
        while not log.empty():
            result.append(log.get())
        for item in result:
            log.put(item)
        return result
