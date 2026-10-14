import json
import os
import re
from base64 import b64encode
from unittest.mock import MagicMock, Mock

import pytest
from rest_framework.serializers import ValidationError

from pulpcore.app.models import (
    CompositeContentGuard,
    ContentRedirectContentGuard,
    EnvVarHeaderContentGuard,
    HeaderContentGuard,
)
from pulpcore.app.serializers import EnvVarHeaderContentGuardSerializer
from pulpcore.plugin.exceptions import ContentGuardRequiresAuthentication

ENVVAR_HEADER = "X-Test-Content-Guard-Header"
ENVVAR_NAME = "ENVVAR_HEADER_GUARD_TEST_SECRET"


def _encode_envvar_secret(secret):
    return b64encode(secret.encode("utf-8")).decode("ascii")


def _envvar_guard(env_var=ENVVAR_NAME):
    return EnvVarHeaderContentGuard(
        name="envvar_header_guard",
        header_name=ENVVAR_HEADER,
        env_var=env_var,
    )


def _envvar_request(header_value=None, header_name=ENVVAR_HEADER):
    request = Mock()
    headers = {}
    if header_value is not None:
        headers[header_name] = header_value
    request.headers = headers
    return request


@pytest.fixture
def envvar_header_secret():
    secret = os.environ.get(ENVVAR_NAME)
    if secret is None or secret.rstrip("\r\n") == "":
        pytest.skip(f"{ENVVAR_NAME} not set")
    return secret.rstrip("\r\n")


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


def test_header_content_guard(db):
    """Test HeaderContentGuard to protect content based on a specific header."""

    content_guard = HeaderContentGuard(
        name="header_guard",
        header_name="x-header-name",
        jq_filter=".this.is.a.path",
        header_value="somevalue",
    )

    request = Mock()

    # Try without any header
    request.headers = {}
    with pytest.raises(PermissionError):
        content_guard.permit(request)

    # Try with a wrong header_name
    request.headers = {"x-burger": "food"}
    with pytest.raises(PermissionError):
        content_guard.permit(request)

    # Try the right header with a non base64 encoded content
    request.headers = {"x-header-name": "somestring"}
    with pytest.raises(PermissionError):
        content_guard.permit(request)

    # Try the right header and a wrong value correctly encoded
    header_value = b64encode(b"anything_here")
    request.headers = {"x-header-name": header_value}
    with pytest.raises(PermissionError):
        content_guard.permit(request)

    # Try the right header with the wrong jq_filter
    # but right value
    header_value = json.dumps({"this": {"is": {"not_a": {"path": "somevalue"}}}})
    encoded_value = b64encode(bytes(header_value, "ascii"))

    request.headers = {"x-header-name": encoded_value}
    with pytest.raises(PermissionError):
        content_guard.permit(request)

    # Try the right header, right jq_filter but wrong value
    header_value = json.dumps({"this": {"is": {"a": {"path": "anything_here"}}}})
    encoded_value = b64encode(bytes(header_value, "ascii"))

    request.headers = {"x-header-name": encoded_value}
    with pytest.raises(PermissionError):
        content_guard.permit(request)

    # Try the right header, json_access and value.
    header_value = json.dumps({"this": {"is": {"a": {"path": "somevalue"}}}})
    encoded_value = b64encode(bytes(header_value, "ascii"))

    request.headers = {"x-header-name": encoded_value}
    assert not content_guard.permit(request)

    # Try to use a value that is not a JSON.
    content_guard_without_jq_filter = HeaderContentGuard(
        name="header_guard", header_name="x-header-name", header_value="somevalue"
    )

    encoded_value = b64encode(b"somevalue")
    request.headers = {"x-header-name": encoded_value}
    assert not content_guard_without_jq_filter.permit(request)


def test_envvar_header_content_guard_allows_matching_header(db, envvar_header_secret):
    _envvar_guard().permit(_envvar_request(_encode_envvar_secret(envvar_header_secret)))


def test_envvar_header_content_guard_denies_missing_header(db, envvar_header_secret):
    with pytest.raises(PermissionError, match="Header X-Test-Content-Guard-Header not found"):
        _envvar_guard().permit(_envvar_request())


def test_envvar_header_content_guard_denies_wrong_header_name(db, envvar_header_secret):
    with pytest.raises(PermissionError):
        _envvar_guard().permit(
            _envvar_request(
                _encode_envvar_secret(envvar_header_secret), header_name="X-Other-Header"
            )
        )


def test_envvar_header_content_guard_denies_invalid_base64(db, envvar_header_secret):
    with pytest.raises(PermissionError, match="not Base64 encoded"):
        _envvar_guard().permit(_envvar_request("!!!c3VwZXItc2VjcmV0LXZhbHVl!!!"))


def test_envvar_header_content_guard_denies_non_base64_header(db, envvar_header_secret):
    with pytest.raises(PermissionError, match="not Base64 encoded"):
        _envvar_guard().permit(_envvar_request("A"))


def test_envvar_header_content_guard_denies_invalid_utf8(db, envvar_header_secret):
    with pytest.raises(PermissionError, match="not valid UTF-8"):
        _envvar_guard().permit(_envvar_request(b64encode(b"\xff\xfe").decode("ascii")))


def test_envvar_header_content_guard_denies_wrong_value(db, envvar_header_secret, caplog):
    caplog.set_level("WARNING")
    with pytest.raises(PermissionError, match="Access denied"):
        _envvar_guard().permit(_envvar_request(_encode_envvar_secret("wrong-value")))
    assert any(
        record.levelname == "WARNING"
        and record.message
        == "Access not allowed. Header value does not match environment variable."
        for record in caplog.records
    )


def test_envvar_header_content_guard_denies_env_var_not_in_allowlist(db, caplog):
    caplog.set_level("WARNING")
    with pytest.raises(PermissionError, match="Access denied"):
        _envvar_guard(env_var="HOME").permit(_envvar_request("not-base64"))
    assert any(
        record.levelname == "WARNING" and "Environment variable HOME is not in" in record.message
        for record in caplog.records
    )


def test_envvar_header_content_guard_denies_empty_env_var(db, monkeypatch):
    monkeypatch.setenv(ENVVAR_NAME, "")
    with pytest.raises(PermissionError, match="Access denied"):
        _envvar_guard().permit(_envvar_request("not-base64"))


def test_envvar_header_content_guard_serializer_rejects_disallowed_env_var(db):
    serializer = EnvVarHeaderContentGuardSerializer()
    with pytest.raises(ValidationError):
        serializer.validate_env_var("DJANGO_SECRET_KEY")


def _composite(*detail_guards):
    composite = MagicMock(spec=CompositeContentGuard)
    composite.guards.all.return_value = [
        MagicMock(cast=MagicMock(return_value=guard)) for guard in detail_guards
    ]
    return composite


def _detail_guard(name, error=None):
    guard = MagicMock()
    guard.name = name
    if error is not None:
        guard.permit.side_effect = error
    return guard


def test_content_guard_authentication_error_is_not_permission_error():
    assert not issubclass(ContentGuardRequiresAuthentication, PermissionError)


def test_content_guard_authentication_error_carries_challenge():
    error = ContentGuardRequiresAuthentication(
        "Authentication required.", challenge='Basic realm="example"'
    )

    assert str(error) == "Authentication required."
    assert error.challenge == 'Basic realm="example"'


def test_composite_authentication_error_does_not_short_circuit_later_success(monkeypatch):
    authentication_guard = _detail_guard(
        "identity",
        ContentGuardRequiresAuthentication("Authentication required.", challenge="Basic"),
    )
    allowing_guard = _detail_guard("origin")
    composite = _composite(authentication_guard, allowing_guard)
    monkeypatch.setattr(
        "pulpcore.app.models.publication.get_url", lambda *_args, **_kwargs: "/guard/"
    )

    CompositeContentGuard.permit(composite, MagicMock())

    authentication_guard.permit.assert_called_once()
    allowing_guard.permit.assert_called_once()


def test_composite_authentication_error_wins_when_all_guards_deny(monkeypatch):
    authentication_guard = _detail_guard(
        "identity",
        ContentGuardRequiresAuthentication("Authentication required.", challenge="Basic"),
    )
    denying_guard = _detail_guard("feature", PermissionError("Access denied."))
    composite = _composite(authentication_guard, denying_guard)
    monkeypatch.setattr(
        "pulpcore.app.models.publication.get_url", lambda *_args, **_kwargs: "/guard/"
    )

    with pytest.raises(ContentGuardRequiresAuthentication) as exc_info:
        CompositeContentGuard.permit(composite, MagicMock())

    assert exc_info.value.challenge == "Basic"


def test_composite_permission_error_when_no_guard_requires_authentication(monkeypatch):
    first_guard = _detail_guard("first", PermissionError("Access denied."))
    second_guard = _detail_guard("second", PermissionError("Access denied."))
    composite = _composite(first_guard, second_guard)
    monkeypatch.setattr(
        "pulpcore.app.models.publication.get_url", lambda *_args, **_kwargs: "/guard/"
    )

    with pytest.raises(PermissionError) as exc_info:
        CompositeContentGuard.permit(composite, MagicMock())

    assert not isinstance(exc_info.value, ContentGuardRequiresAuthentication)
