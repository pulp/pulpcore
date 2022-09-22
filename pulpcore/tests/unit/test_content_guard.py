import pytest
import re

from unittest.mock import Mock

from pulpcore.app.models import ContentRedirectContentGuard


def test_preauthenticate_urls():
    """Test that the redirecting content guard can produce url to the content app."""

    original_url = "http://localhost:8080/pulp/content/dist/"
    content_guard = ContentRedirectContentGuard(name="test")
    content_guard2 = ContentRedirectContentGuard(name="test2")
    signed_url = content_guard.preauthenticate_url(original_url)
    signed_url2 = content_guard2.preauthenticate_url(original_url)

    # analyse signed url
    pattern = re.compile(
        r"^(?P<url>.*)\?expires=(?P<expires>\d*)&validate_token=(?P<salt>.*):(?P<digest>.*)$"
    )
    url_match = pattern.match(signed_url)
    assert bool(url_match)
    assert url_match.group("url") == original_url
    salt = url_match.group("salt")
    digest = url_match.group("digest")
    expires = url_match.group("expires")

    url_match2 = pattern.match(signed_url2)
    assert bool(url_match2)
    assert url_match2.group("url") == original_url
    salt2 = url_match2.group("salt")
    digest2 = url_match2.group("digest")

    request = Mock()

    # Try unsigned url
    request.url = original_url
    request.query = {}
    with pytest.raises(PermissionError):
        content_guard.permit(request)

    # Try valid url
    request.url = signed_url
    request.query = {"expires": expires, "validate_token": ":".join((salt, digest))}
    content_guard.permit(request)

    # Try changed hostname
    request.url = signed_url.replace("localhost", "localnest")
    request.query = {"expires": expires, "validate_token": ":".join((salt, digest))}
    content_guard.permit(request)

    # Try changed distribution
    request.url = signed_url.replace("dist", "publication")
    request.query = {"expires": expires, "validate_token": ":".join((salt, digest))}
    with pytest.raises(PermissionError):
        content_guard.permit(request)

    # Try tempered salt
    request.url = signed_url.replace(salt, salt2)
    request.query = {"expires": expires, "validate_token": ":".join((salt2, digest))}
    with pytest.raises(PermissionError):
        content_guard.permit(request)

    # Try tempered digest
    request.url = signed_url.replace(digest, digest2)
    request.query = {"expires": expires, "validate_token": ":".join((salt, digest2))}
    with pytest.raises(PermissionError):
        content_guard.permit(request)

    # Try tempered expiry
    request.url = signed_url.replace(digest, digest2)
    request.query = {"expires": str(int(expires) + 1), "validate_token": ":".join((salt, digest2))}
    with pytest.raises(PermissionError):
        content_guard.permit(request)
