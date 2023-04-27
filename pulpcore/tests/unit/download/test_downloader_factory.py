import pytest

from pulpcore.download.factory import DownloaderFactory
from pulpcore.plugin.models import Remote


@pytest.mark.asyncio
async def test_user_agent_header():
    remote = Remote(url="http://example.org/", name="foo")
    factory = DownloaderFactory(remote)
    downloader = factory.build(remote.url)
    default_user_agent = DownloaderFactory.user_agent()
    assert downloader.session.headers["User-Agent"] == default_user_agent


@pytest.mark.asyncio
async def test_custom_user_agent_header():
    remote = Remote(url="http://example.org/", headers=[{"User-Agent": "foo"}], name="foo")
    factory = DownloaderFactory(remote)
    downloader = factory.build(remote.url)
    default_user_agent = DownloaderFactory.user_agent()
    expected_user_agent = f"{default_user_agent}, foo"
    assert downloader.session.headers["User-Agent"] == expected_user_agent


@pytest.mark.asyncio
async def test_custom_headers():
    remote = Remote(url="http://example.org/", headers=[{"Connection": "keep-alive"}], name="foo")
    factory = DownloaderFactory(remote)
    downloader = factory.build(remote.url)
    assert downloader.session.headers["Connection"] == "keep-alive"
