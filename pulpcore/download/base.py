from gettext import gettext as _

import asyncio
from collections import namedtuple
import logging
import os
import tempfile
from urllib.parse import urlsplit

from pulpcore.app import pulp_hashlib
from pulpcore.app.models import Artifact
from pulpcore.exceptions import (
    DigestValidationError,
    SizeValidationError,
    TimeoutException,
    UnsupportedDigestValidationError,
)


log = logging.getLogger(__name__)


DownloadResult = namedtuple("DownloadResult", ["url", "artifact_attributes", "path", "headers"])
"""
Args:
    url (str): The url corresponding with the download.
    path (str): The absolute path to the saved file
    artifact_attributes (dict): Contains keys corresponding with
        :class:`~pulpcore.plugin.models.Artifact` fields. This includes the computed digest values
        along with size information.
    headers (aiohttp.multidict.MultiDict): HTTP response headers. The keys are header names. The
        values are header content. None when not using the HttpDownloader or sublclass.
"""


class BaseDownloader:
    """
    The base class of all downloaders, providing digest calculation, validation, and file handling.

    This is an abstract class and is meant to be subclassed. Subclasses are required to implement
    the :meth:`~pulpcore.plugin.download.BaseDownloader.run` method and do two things:

        1. Pass all downloaded data to
           :meth:`~pulpcore.plugin.download.BaseDownloader.handle_data` and schedule it.

        2. Schedule :meth:`~pulpcore.plugin.download.BaseDownloader.finalize` after all data has
           been delivered to :meth:`~pulpcore.plugin.download.BaseDownloader.handle_data`.

    Passing all downloaded data the into
    :meth:`~pulpcore.plugin.download.BaseDownloader.handle_data` allows the file digests to
    be computed while data is written to disk. The digests computed are required if the download is
    to be saved as an :class:`~pulpcore.plugin.models.Artifact` which avoids having to re-read the
    data later.

    The :meth:`~pulpcore.plugin.download.BaseDownloader.handle_data` method by default
    writes to a random file in the current working directory.

    The call to :meth:`~pulpcore.plugin.download.BaseDownloader.finalize` ensures that all
    data written to the file-like object is quiesced to disk before the file-like object has
    `close()` called on it.

    Attributes:
        url (str): The url to download.
        expected_digests (dict): Keyed on the algorithm name provided by hashlib and stores the
            value of the expected digest. e.g. {'md5': '912ec803b2ce49e4a541068d495ab570'}
        expected_size (int): The number of bytes the download is expected to have.
        path (str): The full path to the file containing the downloaded data.
    """

    def __init__(
        self,
        url,
        expected_digests=None,
        expected_size=None,
        semaphore=None,
        *args,
        **kwargs,
    ):
        """
        Create a BaseDownloader object. This is expected to be called by all subclasses.

        Args:
            url (str): The url to download.
            expected_digests (dict): Keyed on the algorithm name provided by hashlib and stores the
                value of the expected digest. e.g. {'md5': '912ec803b2ce49e4a541068d495ab570'}
            expected_size (int): The number of bytes the download is expected to have.
            semaphore (asyncio.Semaphore): A semaphore the downloader must acquire before running.
                Useful for limiting the number of outstanding downloaders in various ways.
        """

        self.url = url
        self._writer = None
        self.path = None
        self.expected_digests = expected_digests
        self.expected_size = expected_size
        if semaphore:
            self.semaphore = semaphore
        else:
            self.semaphore = asyncio.Semaphore()  # This will always be acquired
        self._digests = {}
        self._size = 0
        if self.expected_digests:
            if not set(self.expected_digests).intersection(set(Artifact.DIGEST_FIELDS)):
                raise UnsupportedDigestValidationError(
                    _(
                        "Content at the URL '{}' does not contain at least one trusted hasher which"
                        " is specified in the 'ALLOWED_CONTENT_CHECKSUMS' setting ({}). The"
                        " downloader expected one of the following hashers: {}"
                    ).format(self.url, Artifact.DIGEST_FIELDS, set(self.expected_digests))
                )

    def _ensure_writer_has_open_file(self):
        """
        Create a temporary file on demand.

        Create a temporary file when it's actually used,
        allowing plugin writers to instantiate many downloaders in memory.
        """
        if not self._writer:
            filename = urlsplit(self.url).path.split("/")[-1]
            # linux allows any character except NUL or / in a filename and has a length limit of
            # 255. Making it urlencoding-aware would be nice, but not critical, because urlencoded
            # paths should be OK
            is_legal_filename = filename and (len(filename) <= 243)  # 255 - prefix length
            # if the filename isn't legal then we just fall back to no suffix (random name)
            suffix = "-" + filename if is_legal_filename else None
            # write the file to the current working directory with a random prefix and the
            # desired suffix. we always want the random prefix as it is possible to download
            # the same filename from two different URLs, and the files may not be the same.
            self._writer = tempfile.NamedTemporaryFile(dir=".", suffix=suffix, delete=False)
            self.path = self._writer.name
            self._digests = {n: pulp_hashlib.new(n) for n in Artifact.DIGEST_FIELDS}
            self._size = 0

    async def handle_data(self, data):
        """
        A coroutine that writes data to the file object and compute its digests.

        All subclassed downloaders are expected to pass all data downloaded to this method. Similar
        to the hashlib docstring, repeated calls are equivalent to a single call with
        the concatenation of all the arguments: m.handle_data(a); m.handle_data(b) is equivalent to
        m.handle_data(a+b).

        Args:
            data (bytes): The data to be handled by the downloader.
        """
        self._ensure_writer_has_open_file()
        self._writer.write(data)
        self._record_size_and_digests_for_data(data)

    async def finalize(self):
        """
        A coroutine to flush downloaded data, close the file writer, and validate the data.

        All subclasses are required to call this method after all data has been passed to
        :meth:`~pulpcore.plugin.download.BaseDownloader.handle_data`.

        Raises:
            :class:`~pulpcore.exceptions.DigestValidationError`: When any of the ``expected_digest``
                values don't match the digest of the data passed to
                :meth:`~pulpcore.plugin.download.BaseDownloader.handle_data`.
            :class:`~pulpcore.exceptions.SizeValidationError`: When the ``expected_size`` value
                doesn't match the size of the data passed to
                :meth:`~pulpcore.plugin.download.BaseDownloader.handle_data`.
        """
        self._ensure_writer_has_open_file()
        self._writer.flush()
        os.fsync(self._writer.fileno())
        self._writer.close()
        self._writer = None
        self.validate_digests()
        self.validate_size()
        log.debug(f"Downloaded file from {self.url}")

    def fetch(self):
        """
        Run the download synchronously and return the `DownloadResult`.

        Returns:
            :class:`~pulpcore.plugin.download.DownloadResult`

        Raises:
            Exception: Any fatal exception emitted during downloading
        """
        done, _ = asyncio.get_event_loop().run_until_complete(asyncio.wait([self.run()]))
        return done.pop().result()

    def _record_size_and_digests_for_data(self, data):
        """
        Record the size and digest for an available chunk of data.

        Args:
            data (bytes): The data to have its size and digest values recorded.
        """
        for algorithm in self._digests.values():
            algorithm.update(data)
        self._size += len(data)

    @property
    def artifact_attributes(self):
        """
        A property that returns a dictionary with size and digest information. The keys of this
        dictionary correspond with :class:`~pulpcore.plugin.models.Artifact` fields.
        """
        attributes = {"size": self._size}
        for algorithm in self._digests:
            attributes[algorithm] = self._digests[algorithm].hexdigest()
        return attributes

    def validate_digests(self):
        """
        Validate all digests validate if ``expected_digests`` is set

        Raises:
            :class:`~pulpcore.exceptions.DigestValidationError`: When any of the ``expected_digest``
                values don't match the digest of the data passed to
                :meth:`~pulpcore.plugin.download.BaseDownloader.handle_data`.
        """
        if self.expected_digests:
            for algorithm, expected_digest in self.expected_digests.items():
                actual_digest = self._digests[algorithm].hexdigest()
                if actual_digest != expected_digest:
                    raise DigestValidationError(actual_digest, expected_digest, url=self.url)

    def validate_size(self):
        """
        Validate the size if ``expected_size`` is set

        Raises:
            :class:`~pulpcore.exceptions.SizeValidationError`: When the ``expected_size`` value
                doesn't match the size of the data passed to
                :meth:`~pulpcore.plugin.download.BaseDownloader.handle_data`.
        """
        if self.expected_size:
            actual_size = self._size
            expected_size = self.expected_size
            if actual_size != expected_size:
                raise SizeValidationError(actual_size, expected_size, url=self.url)

    async def run(self, extra_data=None):
        """
        Run the downloader with concurrency restriction.

        This method acquires `self.semaphore` before calling the actual download implementation
        contained in `_run()`. This ensures that the semaphore stays acquired even as the `backoff`
        decorator on `_run()`, handles backoff-and-retry logic.

        Args:
            extra_data (dict): Extra data passed to the downloader.

        Returns:
            :class:`~pulpcore.plugin.download.DownloadResult` from `_run()`.

        """
        async with self.semaphore:
            try:
                return await self._run(extra_data=extra_data)
            except asyncio.TimeoutError:
                raise TimeoutException(self.url)

    async def _run(self, extra_data=None):
        """
        Run the downloader.

        This is a coroutine that asyncio can schedule to complete downloading. Subclasses are
        required to implement this method and do two things:

        1. Pass all downloaded data to
           :meth:`~pulpcore.plugin.download.BaseDownloader.handle_data`.

        2. Call :meth:`~pulpcore.plugin.download.BaseDownloader.finalize` after all data has
           been delivered to :meth:`~pulpcore.plugin.download.BaseDownloader.handle_data`.

        It is also expected that the subclass implementation return a
        :class:`~pulpcore.plugin.download.DownloadResult` object. The
        ``artifact_attributes`` value of the
        :class:`~pulpcore.plugin.download.DownloadResult` is usually set to the
        :attr:`~pulpcore.plugin.download.BaseDownloader.artifact_attributes` property value.

        This method is called from :meth:`~pulpcore.plugin.download.BaseDownloader.run` which
        handles concurrency restriction. Thus, by the time this method is called, the download can
        occur without violating the concurrency restriction.

        Args:
            extra_data (dict): Extra data passed to the downloader.

        Returns:
            :class:`~pulpcore.plugin.download.DownloadResult`

        Raises:
            Validation errors could be emitted when subclassed implementations call
            :meth:`~pulpcore.plugin.download.BaseDownloader.finalize`.
        """
        raise NotImplementedError("Subclasses must define a _run() method that returns a coroutine")
