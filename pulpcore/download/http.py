import logging

import aiohttp
import backoff

from .base import BaseDownloader, DownloadResult


log = logging.getLogger(__name__)


logging.getLogger("backoff").addHandler(logging.StreamHandler())


def http_giveup(exc):
    """
    Inspect a raised exception and determine if we should give up.

    Do not give up when the status code is one of the following:

        429 - Too Many Requests
        502 - Bad Gateway
        503 - Service Unavailable
        504 - Gateway Timeout

    Args:
        exc (aiohttp.ClientResponseException): The exception to inspect

    Returns:
        True if the download should give up, False otherwise
    """
    return exc.code not in [429, 502, 503, 504]


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
            kwargs (dict): This accepts the parameters of
                :class:`~pulpcore.plugin.download.BaseDownloader`.
        """
        if session:
            self.session = session
            self._close_session_on_finalize = False
        else:
            timeout = aiohttp.ClientTimeout(total=None, sock_connect=600, sock_read=600)
            conn = aiohttp.TCPConnector({"force_close": True})
            self.session = aiohttp.ClientSession(connector=conn, timeout=timeout)
            self._close_session_on_finalize = True
        self.auth = auth
        self.proxy = proxy
        self.proxy_auth = proxy_auth
        self.headers_ready_callback = headers_ready_callback
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

    @backoff.on_exception(
        backoff.expo, aiohttp.ClientResponseError, max_tries=10, giveup=http_giveup
    )
    async def _run(self, extra_data=None):
        """
        Download, validate, and compute digests on the `url`. This is a coroutine.

        This method is decorated with a backoff-and-retry behavior to retry HTTP 429 and
        some 5XX errors. It retries with exponential backoff 10 times before allowing
        a final exception to be raised.

        This method provides the same return object type and documented in
        :meth:`~pulpcore.plugin.download.BaseDownloader._run`.

        Args:
            extra_data (dict): Extra data passed by the downloader.
        """
        async with self.session.get(self.url, proxy=self.proxy, auth=self.auth) as response:
            self.raise_for_status(response)
            to_return = await self._handle_response(response)
            await response.release()
        if self._close_session_on_finalize:
            await self.session.close()
        return to_return
