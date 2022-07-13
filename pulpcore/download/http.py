import logging

import aiohttp
import asyncio
import backoff

from .base import BaseDownloader, DownloadResult
from pulpcore.exceptions import (
    DigestValidationError,
    SizeValidationError,
    TimeoutException,
)


log = logging.getLogger(__name__)


logging.getLogger("backoff").addHandler(logging.StreamHandler())


def http_giveup_handler(exc):
    """
    Inspect a raised exception and determine if we should give up.

    Do not give up when the error is one of the following:

        HTTP 429 - Too Many Requests
        HTTP 5xx - Server errors
        Socket timeout
        TCP disconnect
        Client SSL Error

    Based on the AWS and Google Cloud guidelines:
        https://docs.aws.amazon.com/general/latest/gr/api-retries.html
        https://cloud.google.com/storage/docs/retry-strategy

    Args:
        exc (Exception): The exception to inspect

    Returns:
        True if the download should give up, False otherwise
    """
    if isinstance(exc, aiohttp.ClientResponseError):
        server_error = 500 <= exc.code < 600
        too_many_requests = exc.code == 429
        return not server_error and not too_many_requests

    # any other type of error (pre-filtered by the backoff decorator) shouldn't be fatal
    return False


class HttpDownloader(BaseDownloader):
    """
    An HTTP/HTTPS Downloader built on `aiohttp`.

    This downloader downloads data from one `url` and is not reused.

    The downloader optionally takes a session argument, which is an `aiohttp.ClientSession`. This
    allows many downloaders to share one `aiohttp.ClientSession` which provides a connection pool,
    connection reuse, and keep-alives across multiple downloaders. When creating many downloaders,
    have one session shared by all of your `HttpDownloader` objects.

    A session is optional; if omitted, one session will be created, used for this downloader, and
    then closed when the download is complete. A session that is passed in will not be closed when
    the download is complete.

    If a session is not provided, the one created by HttpDownloader uses non-default timing values.
    Specifically, the "total" timeout is set to None and the "sock_connect" and "sock_read" are both
    5 minutes. For more info on these settings, see the aiohttp docs:
    http://aiohttp.readthedocs.io/en/stable/client_quickstart.html#timeouts Behaviorally, it should
    allow for an active download to be arbitrarily long, while still detecting dead or closed
    sessions even when TCPKeepAlive is disabled.

    If a session is not provided, the one created will force TCP connection closure after each
    request. This is done for compatibility reasons due to various issues related to session
    continuation implementation in various servers.

    `aiohttp.ClientSession` objects allows you to configure options that will apply to all
    downloaders using that session such as auth, timeouts, headers, etc. For more info on these
    options see the `aiohttp.ClientSession` docs for more information:
    http://aiohttp.readthedocs.io/en/stable/client_reference.html#aiohttp.ClientSession

    The `aiohttp.ClientSession` can additionally be configured for SSL configuration by passing in a
    `aiohttp.TCPConnector`. For information on configuring either server or client certificate based
    identity verification, see the aiohttp documentation:
    http://aiohttp.readthedocs.io/en/stable/client.html#ssl-control-for-tcp-sockets

    For more information on `aiohttp.BasicAuth` objects, see their docs:
    http://aiohttp.readthedocs.io/en/stable/client_reference.html#aiohttp.BasicAuth

    Synchronous Download::

        downloader = HttpDownloader('http://example.com/')
        result = downloader.fetch()

    Parallel Download::

        download_coroutines = [
            HttpDownloader('http://example.com/').run(),
            HttpDownloader('http://pulpproject.org/').run(),
        ]

        loop = asyncio.get_event_loop()
        done, not_done = loop.run_until_complete(asyncio.wait(download_coroutines))

        for task in done:
            try:
                task.result()  # This is a DownloadResult
            except Exception as error:
                pass  # fatal exceptions are raised by result()

    The HTTPDownloaders contain automatic retry logic if the server responds with HTTP 429 response.
    The coroutine will automatically retry 10 times with exponential backoff before allowing a
    final exception to be raised.

    Attributes:
        session (aiohttp.ClientSession): The session to be used by the downloader.
        auth (aiohttp.BasicAuth): An object that represents HTTP Basic Authorization or None
        proxy (str): An optional proxy URL or None
        proxy_auth (aiohttp.BasicAuth): An optional object that represents proxy HTTP Basic
            Authorization or None
        headers_ready_callback (callable): An optional callback that accepts a single dictionary
            as its argument. The callback will be called when the response headers are
            available. The dictionary passed has the header names as the keys and header values
            as its values. e.g. `{'Transfer-Encoding': 'chunked'}`. This can also be None.

    This downloader also has all of the attributes of
    :class:`~pulpcore.plugin.download.BaseDownloader`
    """

    def __init__(
        self,
        url,
        session=None,
        auth=None,
        proxy=None,
        proxy_auth=None,
        headers_ready_callback=None,
        headers=None,
        throttler=None,
        max_retries=0,
        **kwargs,
    ):
        """
        Args:
            url (str): The url to download.
            session (aiohttp.ClientSession): The session to be used by the downloader. (optional) If
                not specified it will open the session and close it
            auth (aiohttp.BasicAuth): An object that represents HTTP Basic Authorization (optional)
            proxy (str): An optional proxy URL.
            proxy_auth (aiohttp.BasicAuth): An optional object that represents proxy HTTP Basic
                Authorization.
            headers_ready_callback (callable): An optional callback that accepts a single dictionary
                as its argument. The callback will be called when the response headers are
                available. The dictionary passed has the header names as the keys and header values
                as its values. e.g. `{'Transfer-Encoding': 'chunked'}`
            headers (dict): Headers to be submitted with the request.
            throttler (asyncio_throttle.Throttler): Throttler for asyncio.
            max_retries (int): The maximum number of times to retry a download upon failure.
            kwargs (dict): This accepts the parameters of
                :class:`~pulpcore.plugin.download.BaseDownloader`.
        """
        if session:
            self.session = session
            self._close_session_on_finalize = False
        else:
            timeout = aiohttp.ClientTimeout(total=None, sock_connect=600, sock_read=600)
            conn = aiohttp.TCPConnector({"force_close": True})
            self.session = aiohttp.ClientSession(
                connector=conn, timeout=timeout, headers=headers, requote_redirect_url=False
            )
            self._close_session_on_finalize = True
        self.auth = auth
        self.proxy = proxy
        self.proxy_auth = proxy_auth
        self.headers_ready_callback = headers_ready_callback
        self.download_throttler = throttler
        self.max_retries = max_retries
        super().__init__(url, **kwargs)

    def raise_for_status(self, response):
        """
        Raise error if aiohttp response status is >= 400 and not silenced.

        Args:
            response (aiohttp.ClientResponse): The response to handle.

        Raises:
               aiohttp.ClientResponseError: When the response status is >= 400.
        """
        response.raise_for_status()

    async def _handle_response(self, response):
        """
        Handle the aiohttp response by writing it to disk and calculating digests

        Args:
            response (aiohttp.ClientResponse): The response to handle.

        Returns:
             DownloadResult: Contains information about the result. See the DownloadResult docs for
                 more information.
        """
        if self.headers_ready_callback:
            await self.headers_ready_callback(response.headers)
        while True:
            chunk = await response.content.read(1048576)  # 1 megabyte
            if not chunk:
                await self.finalize()
                break  # the download is done
            await self.handle_data(chunk)
        return DownloadResult(
            path=self.path,
            artifact_attributes=self.artifact_attributes,
            url=self.url,
            headers=response.headers,
        )

    async def run(self, extra_data=None):
        """
        Run the downloader with concurrency restriction and retry logic.

        This method acquires `self.semaphore` before calling the actual download implementation
        contained in `_run()`. This ensures that the semaphore stays acquired even as the `backoff`
        wrapper around `_run()`, handles backoff-and-retry logic.

        Args:
            extra_data (dict): Extra data passed to the downloader.

        Returns:
            :class:`~pulpcore.plugin.download.DownloadResult` from `_run()`.

        """
        retryable_errors = (
            aiohttp.ClientConnectorSSLError,
            aiohttp.ClientConnectorError,
            aiohttp.ClientOSError,
            aiohttp.ClientPayloadError,
            aiohttp.ClientResponseError,
            aiohttp.ServerDisconnectedError,
            TimeoutError,
            TimeoutException,
            DigestValidationError,
            SizeValidationError,
        )

        async with self.semaphore:

            @backoff.on_exception(
                backoff.expo,
                retryable_errors,
                max_tries=self.max_retries + 1,
                giveup=http_giveup_handler,
            )
            async def download_wrapper():
                self._ensure_no_broken_file()
                try:
                    return await self._run(extra_data=extra_data)
                except asyncio.TimeoutError:
                    raise TimeoutException(self.url)
                except aiohttp.ClientHttpProxyError as e:
                    log.error(
                        "Proxy {!r} rejected connection request during a request to "
                        "{!r}, status={}, message={!r}".format(
                            e.request_info.real_url,
                            e.request_info.url,
                            e.status,
                            e.message,
                        )
                    )
                    raise e

            return await download_wrapper()

    async def _run(self, extra_data=None):
        """
        Download, validate, and compute digests on the `url`. This is a coroutine.

        This method is externally wrapped with backoff-and-retry behavior for some errors.
        It retries with exponential backoff some number of times before allowing a final
        exception to be raised.

        This method provides the same return object type and documented in
        :meth:`~pulpcore.plugin.download.BaseDownloader._run`.

        Args:
            extra_data (dict): Extra data passed by the downloader.
        """
        if self.download_throttler:
            await self.download_throttler.acquire()
        async with self.session.get(
            self.url, proxy=self.proxy, proxy_auth=self.proxy_auth, auth=self.auth
        ) as response:
            self.raise_for_status(response)
            to_return = await self._handle_response(response)
            await response.release()
        if self._close_session_on_finalize:
            await self.session.close()
        return to_return

    def _ensure_no_broken_file(self):
        """Upon retry reset writer back to None to get a fresh file."""
        if self._writer is not None:
            self._writer.delete = True
            self._writer.close()
            self._writer = None
