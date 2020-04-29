import asyncio
import atexit
import copy
from gettext import gettext as _
import ssl
from tempfile import NamedTemporaryFile
from urllib.parse import urlparse

import aiohttp

from .http import HttpDownloader
from .file import FileDownloader


PROTOCOL_MAP = {"http": HttpDownloader, "https": HttpDownloader, "file": FileDownloader}


class DownloaderFactory:
    """
    A factory for creating downloader objects that are configured from with remote settings.

    The DownloadFactory correctly handles SSL settings, basic auth settings, proxy settings, and
    connection limit settings.

    It supports handling urls with the `http`, `https`, and `file` protocols. The
    ``downloader_overrides`` option allows the caller to specify the download class to be used for
    any given protocol. This allows the user to specify custom, subclassed downloaders to be built
    by the factory.

    Usage::

        the_factory = DownloaderFactory(remote)
        downloader = the_factory.build(url_a)
        result = downloader.fetch()  # 'result' is a DownloadResult

    For http and https urls, in addition to the remote settings, non-default timing values are used.
    Specifically, the "total" timeout is set to None and the "sock_connect" and "sock_read" are both
    5 minutes. For more info on these settings, see the aiohttp docs:
    http://aiohttp.readthedocs.io/en/stable/client_quickstart.html#timeouts Behaviorally, it should
    allow for an active download to be arbitrarily long, while still detecting dead or closed
    sessions even when TCPKeepAlive is disabled.

    Also for http and https urls, even though HTTP 1.1 is used, the TCP connection is setup and
    closed with each request. This is done for compatibility reasons due to various issues related
    to session continuation implementation in various servers.
    """

    def __init__(self, remote, downloader_overrides=None):
        """
        Args:
            remote (:class:`~pulpcore.plugin.models.Remote`): The remote used to populate
                downloader settings.
            downloader_overrides (dict): Keyed on a scheme name, e.g. 'https' or 'ftp' and the value
                is the downloader class to be used for that scheme, e.g.
                {'https': MyCustomDownloader}. These override the default values.
        """
        self._remote = remote
        self._download_class_map = copy.copy(PROTOCOL_MAP)
        if downloader_overrides:
            for protocol, download_class in downloader_overrides.items():  # overlay the overrides
                self._download_class_map[protocol] = download_class
        self._handler_map = {
            "https": self._http_or_https,
            "http": self._http_or_https,
            "file": self._generic,
        }
        self._session = self._make_aiohttp_session_from_remote()
        self._semaphore = asyncio.Semaphore(value=remote.download_concurrency)
        atexit.register(self._session.close)

    def _make_aiohttp_session_from_remote(self):
        """
        Build a :class:`aiohttp.ClientSession` from the remote's settings and timing settings.

        This method is what provides the force_close of the TCP connection with each request.

        Returns:
            :class:`aiohttp.ClientSession`
        """
        tcp_conn_opts = {"force_close": True}

        sslcontext = None
        if self._remote.ca_cert:
            sslcontext = ssl.create_default_context(cadata=self._remote.ca_cert)
        if self._remote.client_key and self._remote.client_cert:
            if not sslcontext:
                sslcontext = ssl.create_default_context()
            with NamedTemporaryFile() as key_file:
                key_file.write(bytes(self._remote.client_key, "utf-8"))
                key_file.flush()
                with NamedTemporaryFile() as cert_file:
                    cert_file.write(bytes(self._remote.client_cert, "utf-8"))
                    cert_file.flush()
                    sslcontext.load_cert_chain(cert_file.name, key_file.name)
        if not self._remote.tls_validation:
            if not sslcontext:
                sslcontext = ssl.create_default_context()
            sslcontext.check_hostname = False
            sslcontext.verify_mode = ssl.CERT_NONE
        if sslcontext:
            tcp_conn_opts["ssl_context"] = sslcontext

        conn = aiohttp.TCPConnector(**tcp_conn_opts)

        timeout = aiohttp.ClientTimeout(total=None, sock_connect=600, sock_read=600)
        return aiohttp.ClientSession(connector=conn, timeout=timeout)

    def build(self, url, **kwargs):
        """
        Build a downloader which can optionally verify integrity using either digest or size.

        The built downloader also provides concurrency restriction if specified by the remote.

        Args:
            url (str): The download URL.
            kwargs (dict): All kwargs are passed along to the downloader. At a minimum, these
                include the :class:`~pulpcore.plugin.download.BaseDownloader` parameters.

        Returns:
            subclass of :class:`~pulpcore.plugin.download.BaseDownloader`: A downloader that
            is configured with the remote settings.
        """
        kwargs["semaphore"] = self._semaphore
        scheme = urlparse(url).scheme.lower()
        try:
            builder = self._handler_map[scheme]
            download_class = self._download_class_map[scheme]
        except KeyError:
            raise ValueError(_("URL: {u} not supported.".format(u=url)))
        else:
            return builder(download_class, url, **kwargs)

    def _http_or_https(self, download_class, url, **kwargs):
        """
        Build a downloader for http:// or https:// URLs.

        Args:
            download_class (:class:`~pulpcore.plugin.download.BaseDownloader`): The download
                class to be instantiated.
            url (str): The download URL.
            kwargs (dict): All kwargs are passed along to the downloader. At a minimum, these
                include the :class:`~pulpcore.plugin.download.BaseDownloader` parameters.

        Returns:
            :class:`~pulpcore.plugin.download.HttpDownloader`: A downloader that
            is configured with the remote settings.
        """
        options = {"session": self._session}
        if self._remote.proxy_url:
            options["proxy"] = self._remote.proxy_url

        if self._remote.username and self._remote.password:
            options["auth"] = aiohttp.BasicAuth(
                login=self._remote.username, password=self._remote.password
            )

        return download_class(url, **options, **kwargs)

    def _generic(self, download_class, url, **kwargs):
        """
        Build a generic downloader based on the url.

        Args:
            download_class (:class:`~pulpcore.plugin.download.BaseDownloader`): The download
                class to be instantiated.
            url (str): The download URL.
            kwargs (dict): All kwargs are passed along to the downloader. At a minimum, these
                include the :class:`~pulpcore.plugin.download.BaseDownloader` parameters.

        Returns:
            subclass of :class:`~pulpcore.plugin.download.BaseDownloader`: A downloader that
            is configured with the remote settings.
        """
        return download_class(url, **kwargs)
