from base64 import b64encode
from unittest.mock import Mock, patch

import pytest
from rest_framework.exceptions import AuthenticationFailed

from pulpcore.app.authentication import JSONHeaderRemoteAuthentication

HEADER = "x-rh-identity"


def get_auth(jq_filter):
    auth = JSONHeaderRemoteAuthentication()
    auth.header = HEADER
    auth.jq_filter = jq_filter
    return auth


def get_request(payload):
    request = Mock()
    request.META = {HEADER: b64encode(payload)}
    return request


def test_environment_is_not_reachable(monkeypatch):
    """A configured filter must not be able to read the environment of the API process."""

    monkeypatch.setenv("PULP_TEST_SECRET", "topsecret")

    with patch("pulpcore.app.authentication.authenticate") as authenticate:
        assert get_auth("env.PULP_TEST_SECRET").authenticate(get_request(b'{"sub": "u"}')) is None

    authenticate.assert_not_called()


def test_invalid_filter_denies():
    with pytest.raises(AuthenticationFailed):
        get_auth("def broken:").authenticate(get_request(b'{"sub": "u"}'))


def test_filter_without_result_denies():
    with pytest.raises(AuthenticationFailed):
        get_auth(".missing[]").authenticate(get_request(b'{"sub": "u"}'))


def test_non_base64_header_denies():
    request = Mock()
    request.META = {HEADER: "é"}

    with pytest.raises(AuthenticationFailed):
        get_auth(".sub").authenticate(request)


def test_valid_filter_authenticates():
    user = Mock()

    with patch("pulpcore.app.authentication.authenticate", return_value=user):
        result = get_auth(".sub").authenticate(get_request(b'{"sub": "u"}'))

    assert result == (user, None)
