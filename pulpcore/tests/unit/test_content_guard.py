import json
import re
from base64 import b64encode
from unittest.mock import Mock

import jq
import pytest

import pulpcore.app.models.publication
from pulpcore.app.models import (
    ContentRedirectContentGuard,
    HeaderContentGuard,
)


def test_preauthenticate_urls(fake_domain):
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


class TestHeaderContentGuard:
    """Test HeaderContentGuard to protect content based on a specific header."""

    @pytest.fixture()
    def content_guard(self, fake_domain):
        return HeaderContentGuard(
            name="header_guard",
            header_name="x-header-name",
            header_value="somevalue",
        )

    def test_accepts_right_value(self, content_guard):
        request = Mock()
        encoded_value = b64encode(b"somevalue")
        request.headers = {"x-header-name": encoded_value}
        assert content_guard.permit(request) is None


class TestHeaderContentGuardWithJsonPath:
    """Test HeaderContentGuard to protect content based on a specific header."""

    @pytest.fixture()
    def content_guard(self, settings, fake_domain):
        settings.ALLOW_INSECURE_HEADER_CONTENT_GUARD_JQ_PROCESSING_AND_FORFEIT_ALL_COMMUNITY_SUPPORT = False  # noqa
        return HeaderContentGuard(
            name="header_guard",
            header_name="x-header-name",
            jq_filter=".this.is_a.path",
            header_value="somevalue",
        )

    def test_rejects_wrong_value(self, settings, content_guard):
        settings.ALLOW_INSECURE_HEADER_CONTENT_GUARD_JQ_PROCESSING_AND_FORFEIT_ALL_COMMUNITY_SUPPORT = False  # noqa

        request = Mock()
        header_value = json.dumps({"this": {"is_a": {"path": "othervalue"}}})
        encoded_value = b64encode(bytes(header_value, "ascii"))

        request.headers = {"x-header-name": encoded_value}
        with pytest.raises(PermissionError):
            content_guard.permit(request)

    def test_rejects_value_in_wrong_path(self, settings, content_guard):
        settings.ALLOW_INSECURE_HEADER_CONTENT_GUARD_JQ_PROCESSING_AND_FORFEIT_ALL_COMMUNITY_SUPPORT = False  # noqa

        request = Mock()
        header_value = json.dumps({"this": {"is": {"not_the": {"path": "somevalue"}}}})
        encoded_value = b64encode(bytes(header_value, "ascii"))

        request.headers = {"x-header-name": encoded_value}
        with pytest.raises(PermissionError):
            content_guard.permit(request)

    def test_accepts_value_in_path(self, settings, content_guard):
        settings.ALLOW_INSECURE_HEADER_CONTENT_GUARD_JQ_PROCESSING_AND_FORFEIT_ALL_COMMUNITY_SUPPORT = False  # noqa

        request = Mock()
        header_value = json.dumps({"this": {"is_a": {"path": "somevalue"}}})
        encoded_value = b64encode(bytes(header_value, "ascii"))

        request.headers = {"x-header-name": encoded_value}
        assert content_guard.permit(request) is None


class TestHeaderContentGuardWithJqFilter:
    """Test HeaderContentGuard to protect content based on a specific header using jq_filter."""

    @pytest.fixture()
    def content_guard(self, fake_domain, settings, monkeypatch):
        settings.ALLOW_INSECURE_HEADER_CONTENT_GUARD_JQ_PROCESSING_AND_FORFEIT_ALL_COMMUNITY_SUPPORT = True  # noqa
        # Fake that we imported jq according to the (to late) changed settings.
        monkeypatch.setattr(pulpcore.app.models.publication, "jq", jq, raising=False)

        return HeaderContentGuard(
            name="header_guard",
            header_name="x-header-name",
            jq_filter=".this.is.a|{path}.path",
            header_value="somevalue",
        )

    def test_rejects_request_without_any_header(self, content_guard):
        request = Mock()
        request.headers = {}

        with pytest.raises(PermissionError):
            content_guard.permit(request)

    def test_rejects_request_with_wrong_header(self, content_guard):
        request = Mock()
        request.headers = {"x-burger": "food"}

        with pytest.raises(PermissionError):
            content_guard.permit(request)

    def test_rejects_request_with_value_not_base64(self, content_guard):
        request = Mock()
        request.headers = {"x-header-name": "somestring"}

        with pytest.raises(PermissionError):
            content_guard.permit(request)

    def test_rejects_request_with_wrong_base64_value(self, content_guard):
        request = Mock()
        header_value = b64encode(b"anything_here")
        request.headers = {"x-header-name": header_value}

        with pytest.raises(PermissionError):
            content_guard.permit(request)

    def test_rejects_request_with_value_in_wrong_path(self, content_guard):
        request = Mock()
        header_value = json.dumps({"this": {"is": {"not_a": {"path": "somevalue"}}}})
        encoded_value = b64encode(bytes(header_value, "ascii"))
        request.headers = {"x-header-name": encoded_value}

        with pytest.raises(PermissionError):
            content_guard.permit(request)

    def test_rejects_request_with_wrong_value_in_right_path(self, content_guard):
        request = Mock()
        header_value = json.dumps({"this": {"is": {"a": {"path": "anything_here"}}}})
        encoded_value = b64encode(bytes(header_value, "ascii"))
        request.headers = {"x-header-name": encoded_value}

        with pytest.raises(PermissionError):
            content_guard.permit(request)

    def test_accepts_request_with_right_value_in_right_path(self, content_guard):
        request = Mock()
        header_value = json.dumps({"this": {"is": {"a": {"path": "somevalue"}}}})
        encoded_value = b64encode(bytes(header_value, "ascii"))
        request.headers = {"x-header-name": encoded_value}

        assert content_guard.permit(request) is None

    def test_jq_feature_flag(self, settings, caplog, content_guard):
        settings.ALLOW_INSECURE_HEADER_CONTENT_GUARD_JQ_PROCESSING_AND_FORFEIT_ALL_COMMUNITY_SUPPORT = False  # noqa
        caplog.set_level("WARNING")

        request = Mock()
        header_value = json.dumps({"this": {"is": {"a": {"path": "somevalue"}}}})
        encoded_value = b64encode(bytes(header_value, "ascii"))
        request.headers = {"x-header-name": encoded_value}

        with pytest.raises(PermissionError):
            content_guard.permit(request)

        print(caplog.records)
        assert any(
            record.levelname == "WARNING"
            and record.message
            == "Using 'jq_filter' is only allowed with simple paths on this installation."
            for record in caplog.records
        )


class TestHeaderContentGuardWithJqFilterExploitEnvOracle:
    @pytest.fixture()
    def content_guard(self, fake_domain, settings, monkeypatch):
        monkeypatch.setenv("SECRET", "HONEYPOT")
        settings.ALLOW_INSECURE_HEADER_CONTENT_GUARD_JQ_PROCESSING_AND_FORFEIT_ALL_COMMUNITY_SUPPORT = True  # noqa
        # Fake that we imported jq according to the (to late) changed settings.
        monkeypatch.setattr(pulpcore.app.models.publication, "jq", jq, raising=False)

        return HeaderContentGuard(
            name="header_guard",
            header_name="x-header-name",
            jq_filter='"t"',
            header_value="t",
        )

    def test_cannot_read_env(self, content_guard):
        content_guard.jq_filter = 'if (env.SECRET[.pos:.pos+1] == .char) then "t" else "f" end'

        request = Mock()
        header_value = json.dumps({"pos": 3, "char": "E"})
        encoded_value = b64encode(bytes(header_value, "ascii"))
        request.headers = {"x-header-name": encoded_value}

        with pytest.raises(PermissionError):
            content_guard.permit(request)

    def test_cannot_read_dollar_env(self, content_guard):
        content_guard.jq_filter = 'if ($ENV.SECRET[.pos:.pos+1] == .char) then "t" else "f" end'

        request = Mock()
        header_value = json.dumps({"pos": 3, "char": "E"})
        encoded_value = b64encode(bytes(header_value, "ascii"))
        request.headers = {"x-header-name": encoded_value}

        with pytest.raises(PermissionError):
            content_guard.permit(request)
