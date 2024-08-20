import os

from urllib.parse import urlparse

import aiofiles

from .base import BaseDownloader, DownloadResult


class FileDownloader(BaseDownloader):
    """
    A downloader for downloading files from the filesystem.

    It provides digest and size validation along with computation of the digests needed to save the
    file as an Artifact. It writes a new file to the disk and the return path is included in the
    [pulpcore.plugin.download.DownloadResult][].

    This downloader has all of the attributes of
    [pulpcore.plugin.download.BaseDownloader][]
    """

    def __init__(self, url, *args, **kwargs):
        """
        Download files from a url that starts with `file://`

        Args:
            url (str): The url to the file. This is expected to begin with `file://`
            kwargs (dict): This accepts the parameters of
                [pulpcore.plugin.download.BaseDownloader][].

        Raises:
            ValidationError: When the url starts with `file://`, but is not a subfolder of a path in
                the ALLOWED_IMPORT_PATH setting.
        """
        from pulpcore.app.serializers import RemoteSerializer

        RemoteSerializer().validate_url(url)
        p = urlparse(url)
        self._path = os.path.abspath(os.path.join(p.netloc, p.path))
        super().__init__(url, *args, **kwargs)

    async def _run(self, extra_data=None):
        """
        Read, validate, and compute digests on the `url`. This is a coroutine.

        This method provides the same return object type and documented in
        :meth:`~pulpcore.plugin.download.BaseDownloader._run`.

        Args:
            extra_data (dict): Extra data passed to the downloader.
        """
        async with aiofiles.open(self._path, "rb") as f_handle:
            while True:
                chunk = await f_handle.read(1048576)  # 1 megabyte
                if not chunk:
                    await self.finalize()
                    break  # the reading is done
                await self.handle_data(chunk)
            return DownloadResult(
                path=self.path,
                artifact_attributes=self.artifact_attributes,
                url=self.url,
                headers=None,
            )
