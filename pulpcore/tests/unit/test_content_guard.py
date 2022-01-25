import re

from unittest import TestCase
from unittest.mock import Mock

from pulpcore.app.models import ContentRedirectContentGuard


class RedirectingContentGuardTestCase(TestCase):
    """Tests that the redirecting content guard can produce url to the content app."""

    def test_preauthenticate_urls(self):
        """Test that the redirecting content guard can produce url to the content app."""

        original_url = "http://localhost:8080/pulp/content/dist/"
        content_guard = ContentRedirectContentGuard(name="test")
        content_guard2 = ContentRedirectContentGuard(name="test2")
        signed_url = content_guard.preauthenticate_url(original_url)
        signed_url2 = content_guard2.preauthenticate_url(original_url)

        # analyse signed url
        pattern = re.compile(r"^(?P<url>.*)\?validate_token=(?P<salt>.*):(?P<digest>.*)$")
        url_match = pattern.match(signed_url)
        self.assertTrue(bool(url_match))
        self.assertEqual(url_match.group("url"), original_url)
        salt = url_match.group("salt")
        digest = url_match.group("digest")

        url_match2 = pattern.match(signed_url2)
        self.assertTrue(bool(url_match2))
        self.assertEqual(url_match2.group("url"), original_url)
        salt2 = url_match2.group("salt")
        digest2 = url_match2.group("digest")

        request = Mock()

        # Try unsigned url
        request.url = original_url
        request.query = {}
        with self.assertRaises(PermissionError):
            content_guard.permit(request)

        # Try valid url
        request.url = signed_url
        request.query = {"validate_token": ":".join((salt, digest))}
        content_guard.permit(request)

        # Try changed hostname
        request.url = signed_url.replace("localhost", "localnest")
        request.query = {"validate_token": ":".join((salt, digest))}
        content_guard.permit(request)

        # Try changed distribution
        request.url = signed_url.replace("dist", "publication")
        request.query = {"validate_token": ":".join((salt, digest))}
        with self.assertRaises(PermissionError):
            content_guard.permit(request)

        # Try tempered salt
        request.url = signed_url.replace(salt, salt2)
        request.query = {"validate_token": ":".join((salt2, digest))}
        with self.assertRaises(PermissionError):
            content_guard.permit(request)

        # Try tempered digest
        request.url = signed_url.replace(digest, digest2)
        request.query = {"validate_token": ":".join((salt, digest2))}
        with self.assertRaises(PermissionError):
            content_guard.permit(request)
