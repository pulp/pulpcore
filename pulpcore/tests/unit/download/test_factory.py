from django.test import TestCase

from pulpcore.download.factory import DownloaderFactory, user_agent
from pulpcore.plugin.models import Remote


class DownloaderFactoryHeadersTestCase(TestCase):
    def test_user_agent_header(self):
        remote = Remote.objects.create(url="http://example.org/", name="foo")
        factory = DownloaderFactory(remote)
        downloader = factory.build(remote.url)
        default_user_agent = user_agent()
        self.assertEqual(downloader.session.headers["User-Agent"], default_user_agent)
        remote.delete()

    def test_custom_user_agent_header(self):
        remote = Remote.objects.create(
            url="http://example.org/", headers=[{"User-Agent": "foo"}], name="foo"
        )
        factory = DownloaderFactory(remote)
        downloader = factory.build(remote.url)
        default_user_agent = user_agent()
        expected_user_agent = f"{default_user_agent}, foo"
        self.assertEqual(downloader.session.headers["User-Agent"], expected_user_agent)
        remote.delete()

    def test_custom_headers(self):
        remote = Remote.objects.create(
            url="http://example.org/", headers=[{"Connection": "keep-alive"}], name="foo"
        )
        factory = DownloaderFactory(remote)
        downloader = factory.build(remote.url)
        self.assertEqual(downloader.session.headers["Connection"], "keep-alive")
