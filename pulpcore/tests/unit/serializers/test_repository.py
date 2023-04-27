import pytest
from types import SimpleNamespace

from unittest.mock import Mock
from rest_framework import serializers

from pulpcore.app import models
from pulpcore.app.serializers import (
    PublicationSerializer,
    RemoteSerializer,
)

pytestmark = pytest.mark.usefixtures("fake_domain")
MINIMAL_DATA = {"name": "test", "url": "http://whatever", "pulp_labels": {}}


def test_validate_proxy_creds_update():
    remote = SimpleNamespace(
        proxy_url="http://whatever",
        proxy_username="user",
        proxy_password="pass",
        **MINIMAL_DATA,
    )
    data = {"proxy_username": "user42"}
    serializer = RemoteSerializer(remote, data=data, partial=True)
    serializer.is_valid(raise_exception=True)


def test_validate_proxy_creds_update_invalid():
    remote = SimpleNamespace(
        proxy_url="http://whatever",
        proxy_username=None,
        proxy_password=None,
        **MINIMAL_DATA,
    )
    data = {"proxy_username": "user"}
    serializer = RemoteSerializer(remote, data=data, partial=True)
    with pytest.raises(serializers.ValidationError, match="can only be specified together"):
        serializer.is_valid(raise_exception=True)


def _gen_remote_serializer():
    remote = SimpleNamespace(
        client_key=None,
        username="user",
        password="pass",
        proxy_url="foobar",
        proxy_username="proxyuser",
        proxy_password="proxypass-EXAMPLE",
        **MINIMAL_DATA,
    )
    serializer = RemoteSerializer(remote)
    # The pulp_href field needs too much things we are not interested in here.
    serializer.fields.pop("pulp_href")
    return serializer


def test_hidden_fields():
    serializer = _gen_remote_serializer()
    fields = serializer.data["hidden_fields"]
    assert fields == [
        {"name": "client_key", "is_set": False},
        {"name": "proxy_username", "is_set": True},
        {"name": "proxy_password", "is_set": True},
        {"name": "username", "is_set": True},
        {"name": "password", "is_set": True},
    ]

    # Test "hidden_fields" is read only
    serializer.data["hidden_fields"] = []
    assert serializer.data["hidden_fields"] != []


def test_validate_repository_only(monkeypatch):
    mock_repo = Mock()
    monkeypatch.setattr(models, "Repository", mock_repo)
    data = {"repository": mock_repo}
    serializer = PublicationSerializer()
    new_data = serializer.validate(data)
    assert new_data == {"repository_version": mock_repo.latest_version.return_value}
    mock_repo.latest_version.assert_called_once_with()


def test_validate_repository_version_only():
    mock_version = Mock()
    data = {"repository_version": mock_version}
    serializer = PublicationSerializer()
    new_data = serializer.validate(data)
    assert new_data == {"repository_version": mock_version}


def test_validate_repository_and_repository_version():
    mock_version = Mock()
    mock_repository = Mock()
    data = {"repository_version": mock_version, "repository": mock_repository}
    serializer = PublicationSerializer()
    with pytest.raises(serializers.ValidationError):
        serializer.validate(data)


def test_validate_no_repository_no_version():
    serializer = PublicationSerializer()
    with pytest.raises(serializers.ValidationError):
        serializer.validate({})


def test_validate_repository_only_unknown_field(monkeypatch):
    mock_repo = Mock()
    monkeypatch.setattr(models, "RepositoryVersion", Mock())
    data = {"repository": mock_repo, "unknown_field": "unknown"}
    serializer = PublicationSerializer(data=data)
    with pytest.raises(serializers.ValidationError):
        serializer.validate(data)


def test_validate_repository_version_only_unknown_field():
    mock_version = Mock()
    data = {"repository_version": mock_version, "unknown_field": "unknown"}
    serializer = PublicationSerializer(data=data)
    with pytest.raises(serializers.ValidationError):
        serializer.validate(data)
