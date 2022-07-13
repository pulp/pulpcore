from aiohttp import __version__ as aiohttp_version
import asyncio
import atexit
import copy
from gettext import gettext as _
from multidict import MultiDict
import platform
from pkg_resources import get_distribution
import ssl
import sys
from tempfile import NamedTemporaryFile
from urllib.parse import urlparse

import aiohttp

from .http import HttpDownloader
from .file import FileDownloader


PROTOCOL_MAP = {
    "http": HttpDownloader,
    "https": HttpDownloader,
    "file": FileDownloader,
}


def user_agent():
    """
    Produce a User-Agent string to identify Pulp and relevant system info.
    """
    pulp_version = get_distribution("pulpcore").version
    python = "{} {}.{}.{}-{}{}".format(sys.implementation.name, *sys.version_info)
    uname = platform.uname()
    system = f"{uname.system} {uname.machine}"
    return f"pulpcore/{pulp_version} ({python}, {system}) (aiohttp {aiohttp_version})"


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
        download_concurrency = remote.download_concurrency or remote.DEFAULT_DOWNLOAD_CONCURRENCY

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
        self._semaphore = asyncio.Semaphore(value=download_concurrency)
        atexit.register(self._session_cleanup)

    def _session_cleanup(self):
        asyncio.get_event_loop().run_until_complete(self._session.close())

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

        headers = MultiDict({"User-Agent": user_agent()})
        if self._remote.headers is not None:
            for header_dict in self._remote.headers:
                user_agent_header = header_dict.pop("User-Agent", None)
                if user_agent_header:
                    headers["User-Agent"] = f"{headers['User-Agent']}, {user_agent_header}"
                headers.extend(header_dict)

        conn = aiohttp.TCPConnector(**tcp_conn_opts)
        total = self._remote.total_timeout
        sock_connect = self._remote.sock_connect_timeout
        sock_read = self._remote.sock_read_timeout
        connect = self._remote.connect_timeout

        timeout = aiohttp.ClientTimeout(
            total=total, sock_connect=sock_connect, sock_read=sock_read, connect=connect
        )
        return aiohttp.ClientSession(
            connector=conn, timeout=timeout, headers=headers, requote_redirect_url=False
        )

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
        kwargs["max_retries"] = (
            kwargs.get("max_retries")
            or self._remote.max_retries
            or self._remote.DEFAULT_MAX_RETRIES
        )

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
            if self._remote.proxy_username and self._remote.proxy_password:
                options["proxy_auth"] = aiohttp.BasicAuth(
                    login=self._remote.proxy_username, password=self._remote.proxy_password
                )

        if self._remote.username and self._remote.password:
            options["auth"] = aiohttp.BasicAuth(
                login=self._remote.username, password=self._remote.password
            )

        kwargs["throttler"] = self._remote.download_throttler if self._remote.rate_limit else None

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
