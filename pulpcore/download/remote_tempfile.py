import os

import asyncio
import aiofiles

from .base import BaseDownloader, DownloadResult
from pulpcore.app.models import RemoteDownload


class TempFileDownloader(BaseDownloader):
    """
    A downloader for hooking onto a download in progress

    This downloader has all of the attributes of
    [pulpcore.plugin.download.BaseDownloader][]
    """

    def __init__(self, url, *args, **kwargs):
        """
        Download files from a url that starts with `tmp://`

        Args:
            url (str): The url to the file. This is expected to begin with `tmp://`
            kwargs (dict): This accepts the parameters of
                [pulpcore.plugin.download.BaseDownloader][].

        Raises:
            AssertionError: When 'sha256' is not in expected_digests, or expected_size is 0
        """
        super().__init__(url, *args, **kwargs)
        assert "sha256" in self.expected_digests
        assert self.expected_size > 0

    async def _run(self, extra_data=None):
        """
        Read, validate, and compute digests on the tempfile. This is a coroutine.

        This method provides the same return object type and documented in
        :meth:`~pulpcore.plugin.download.BaseDownloader._run`.

        Args:
            extra_data (dict): Extra data passed to the downloader.
        """
        retries = 60
        while True:
            res = await RemoteDownload.objects.aget(download_id=self.expected_digests["sha256"])
            if not res.temp_path or not os.path.exists(res.temp_path):
                await asyncio.sleep(1)
                retries -= 1
                if retries == 0:
                    raise Exception(f"{res.temp_path} did not show up in 60 seconds, aborting.")
                continue
            self._path = res.temp_path
            break

        # XXX timeout?
        async with aiofiles.open(self._path, "rb") as f_handle:
            while True:
                chunk = await f_handle.read(1048576)  # 1 megabyte
                if not chunk:
                    if self._size >= self.expected_size:
                        await self.finalize()
                        break
                    await asyncio.sleep(0.5)
                    continue

                await self.handle_data(chunk)
            return DownloadResult(
                path=self.path,
                artifact_attributes=self.artifact_attributes,
                url=self.url,
                headers=None,
            )
