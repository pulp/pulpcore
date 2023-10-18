"""Utilities for tests for the file plugin."""
import aiohttp
import asyncio
import hashlib
import os

from pulpcore.tests.functional.utils import download_file


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


def get_url(url, auth=None, headers=None):
    """
    Performs a GET request on a URL and returns an aiohttp.Response object.
    """
    return asyncio.run(_get_url(url, auth=auth, headers=headers))


async def _get_url(url, auth=None, headers=None):
    async with aiohttp.ClientSession(auth=auth) as session:
        async with session.get(url, verify_ssl=False, headers=headers) as response:
            return response
