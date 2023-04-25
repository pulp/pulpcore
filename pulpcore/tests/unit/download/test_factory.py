from django.test import TestCase
from asgiref.sync import sync_to_async

from pulpcore.download.factory import DownloaderFactory
from pulpcore.plugin.models import Remote


class DownloaderFactoryHeadersTestCase(TestCase):
    async def test_user_agent_header(self):
        remote = await sync_to_async(Remote.objects.create)(url="http://example.org/", name="foo")
        factory = DownloaderFactory(remote)
        downloader = factory.build(remote.url)
        default_user_agent = DownloaderFactory.user_agent()
        self.assertEqual(downloader.session.headers["User-Agent"], default_user_agent)
        await sync_to_async(remote.delete)()

    async def test_custom_user_agent_header(self):
        remote = await sync_to_async(Remote.objects.create)(
            url="http://example.org/", headers=[{"User-Agent": "foo"}], name="foo"
        )
        factory = DownloaderFactory(remote)
        downloader = factory.build(remote.url)
        default_user_agent = DownloaderFactory.user_agent()
        expected_user_agent = f"{default_user_agent}, foo"
        self.assertEqual(downloader.session.headers["User-Agent"], expected_user_agent)
        await sync_to_async(remote.delete)()

    async def test_custom_headers(self):
        remote = await sync_to_async(Remote.objects.create)(
            url="http://example.org/", headers=[{"Connection": "keep-alive"}], name="foo"
        )
        factory = DownloaderFactory(remote)
        downloader = factory.build(remote.url)
        self.assertEqual(downloader.session.headers["Connection"], "keep-alive")
        await sync_to_async(remote.delete)()
