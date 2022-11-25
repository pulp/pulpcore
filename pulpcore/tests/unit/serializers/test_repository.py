from unittest import TestCase
from types import SimpleNamespace

import mock
from rest_framework import serializers

from pulpcore.app.serializers import (
    PublicationSerializer,
    RemoteSerializer,
)


class TestRemoteSerializer(TestCase):
    minimal_data = {"name": "test", "url": "http://whatever", "pulp_labels": {}}

    def test_validate_proxy_creds_update(self):
        remote = SimpleNamespace(
            proxy_url="http://whatever",
            proxy_username="user",
            proxy_password="pass",
            **self.minimal_data,
        )
        data = {"proxy_username": "user42"}
        serializer = RemoteSerializer(remote, data=data, partial=True)
        serializer.is_valid(raise_exception=True)

    def test_validate_proxy_creds_update_invalid(self):
        remote = SimpleNamespace(
            proxy_url="http://whatever",
            proxy_username=None,
            proxy_password=None,
            **self.minimal_data,
        )
        data = {"proxy_username": "user"}
        serializer = RemoteSerializer(remote, data=data, partial=True)
        with self.assertRaises(serializers.ValidationError) as ctx:
            serializer.is_valid(raise_exception=True)
        self.assertIn("can only be specified together", str(ctx.exception))

    def _gen_remote_serializer(self):
        remote = SimpleNamespace(
            client_key=None,
            username="user",
            password="pass",
            proxy_url="foobar",
            proxy_username="proxyuser",
            proxy_password="proxypass",
            **self.minimal_data,
        )
        serializer = RemoteSerializer(remote)
        # The pulp_href field needs too much things we are not interested in here.
        serializer.fields.pop("pulp_href")
        return serializer

    def test_hidden_fields(self):
        serializer = self._gen_remote_serializer()
        fields = serializer.data["hidden_fields"]
        self.assertEqual(
            fields,
            [
                {"name": "client_key", "is_set": False},
                {"name": "proxy_username", "is_set": True},
                {"name": "proxy_password", "is_set": True},
                {"name": "username", "is_set": True},
                {"name": "password", "is_set": True},
            ],
        )

    def test_read_only_hidden_fields(self):
        serializer = self._gen_remote_serializer()
        serializer.data["hidden_fields"] = []

        self.assertNotEqual(serializer.data["hidden_fields"], [])


class TestPublicationSerializer(TestCase):
    @mock.patch("pulpcore.app.serializers.repository.models.Repository")
    def test_validate_repository_only(self, mock_repo):
        data = {"repository": mock_repo}
        serializer = PublicationSerializer()
        new_data = serializer.validate(data)
        self.assertEqual(new_data, {"repository_version": mock_repo.latest_version.return_value})
        mock_repo.latest_version.assert_called_once_with()

    def test_validate_repository_version_only(self):
        mock_version = mock.MagicMock()
        data = {"repository_version": mock_version}
        serializer = PublicationSerializer()
        new_data = serializer.validate(data)
        self.assertEqual(new_data, {"repository_version": mock_version})

    def test_validate_repository_and_repository_version(self):
        mock_version = mock.MagicMock()
        mock_repository = mock.MagicMock()
        data = {"repository_version": mock_version, "repository": mock_repository}
        serializer = PublicationSerializer()
        with self.assertRaises(serializers.ValidationError):
            serializer.validate(data)

    def test_validate_no_repository_no_version(self):
        serializer = PublicationSerializer()
        with self.assertRaises(serializers.ValidationError):
            serializer.validate({})

    @mock.patch("pulpcore.app.serializers.repository.models.RepositoryVersion")
    def test_validate_repository_only_unknown_field(self, mock_version):
        mock_repo = mock.MagicMock()
        data = {"repository": mock_repo, "unknown_field": "unknown"}
        serializer = PublicationSerializer(data=data)
        with self.assertRaises(serializers.ValidationError):
            serializer.validate(data)

    def test_validate_repository_version_only_unknown_field(self):
        mock_version = mock.MagicMock()
        data = {"repository_version": mock_version, "unknown_field": "unknown"}
        serializer = PublicationSerializer(data=data)
        with self.assertRaises(serializers.ValidationError):
            serializer.validate(data)
