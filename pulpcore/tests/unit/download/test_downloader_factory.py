import asyncio
import gc
import weakref

import pytest

from pulpcore.app.util import get_domain
from pulpcore.download import factory as factory_module
from pulpcore.download.factory import DownloaderFactory
from pulpcore.plugin.models import Remote


@pytest.fixture(autouse=True)
def mock_default_domain(db):
    # Cache the domain in synchronous context before starting the tests.
    get_domain()


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


@pytest.mark.asyncio
async def test_factory_is_freed_once_unused():
    remote = Remote(url="http://example.org/", name="foo")
    factory = DownloaderFactory(remote)
    downloader = factory.build(remote.url)
    await downloader.session.close()
    ref = weakref.ref(factory)
    del factory, downloader
    gc.collect()
    assert ref() is None


def test_open_sessions_are_closed_at_exit():
    # At exit no event loop is running, so the hook runs one to completion itself.
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        remote = Remote(url="http://example.org/", name="foo")
        factory = DownloaderFactory(remote)
        assert factory in factory_module._open_factories
        assert not factory._session.closed
        factory_module._close_open_sessions()
        assert factory._session.closed
        # A second run, as at exit after the owner closed the session, does nothing.
        factory_module._close_open_sessions()
    finally:
        asyncio.set_event_loop(None)
        loop.close()
