from unittest import TestCase
from types import SimpleNamespace

import mock
from rest_framework import serializers

from pulpcore.app.models import Distribution
from pulpcore.app.serializers import (
    DistributionSerializer,
    PublicationSerializer,
    RemoteSerializer,
)


class TestRemoteSerializer(TestCase):
    minimal_data = {"name": "test", "url": "http://whatever"}

    def test_minimal_data(self):
        data = {}
        data.update(self.minimal_data)
        serializer = RemoteSerializer(data=data)
        serializer.is_valid(raise_exception=True)

    def test_validate_proxy(self):
        data = {"proxy_url": "http://whatever"}
        data.update(self.minimal_data)
        serializer = RemoteSerializer(data=data)
        serializer.is_valid(raise_exception=True)

    def test_validate_proxy_invalid(self):
        data = {"proxy_url": "http://user:pass@whatever"}
        data.update(self.minimal_data)
        serializer = RemoteSerializer(data=data)
        with self.assertRaises(serializers.ValidationError):
            serializer.is_valid(raise_exception=True)

    def test_validate_proxy_creds(self):
        data = {"proxy_url": "http://whatever", "proxy_username": "user", "proxy_password": "pass"}
        data.update(self.minimal_data)
        serializer = RemoteSerializer(data=data)
        serializer.is_valid(raise_exception=True)

    def test_validate_proxy_creds_invalid(self):
        data = {"proxy_url": "http://whatever", "proxy_username": "user"}
        data.update(self.minimal_data)
        serializer = RemoteSerializer(data=data)
        with self.assertRaises(serializers.ValidationError):
            serializer.is_valid(raise_exception=True)

    def test_validate_proxy_creds_update(self):
        Remote = SimpleNamespace(
            proxy_url="http://whatever",
            proxy_username="user",
            proxy_password="pass",
            **self.minimal_data,
        )
        data = {"proxy_username": "user42"}
        serializer = RemoteSerializer(Remote, data=data, partial=True)
        serializer.is_valid(raise_exception=True)

    def test_validate_proxy_creds_update_invalid(self):
        Remote = SimpleNamespace(
            proxy_url="http://whatever",
            proxy_username=None,
            proxy_password=None,
            **self.minimal_data,
        )
        data = {"proxy_username": "user"}
        serializer = RemoteSerializer(Remote, data=data, partial=True)
        with self.assertRaises(serializers.ValidationError) as ctx:
            serializer.is_valid(raise_exception=True)
        self.assertIn("can only be specified together", str(ctx.exception))


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


class TestDistributionPath(TestCase):
    def test_overlap(self):
        Distribution.objects.create(base_path="foo/bar", name="foobar")
        overlap_errors = {"base_path": ["Overlaps with existing distribution 'foobar'"]}

        # test that the new distribution cannot be nested in an existing path
        data = {"name": "foobarbaz", "base_path": "foo/bar/baz"}
        serializer = DistributionSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertDictEqual(overlap_errors, serializer.errors)

        # test that the new distribution cannot nest an existing path
        data = {"name": "foo", "base_path": "foo"}
        serializer = DistributionSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertDictEqual(overlap_errors, serializer.errors)

    def test_no_overlap(self):
        Distribution.objects.create(base_path="fu/bar", name="fubar")

        # different path
        data = {"name": "fufu", "base_path": "fubar"}
        serializer = DistributionSerializer(data=data)
        self.assertTrue(serializer.is_valid())
        self.assertDictEqual({}, serializer.errors)

        # common base path but different path
        data = {"name": "fufu", "base_path": "fu/baz"}
        serializer = DistributionSerializer(data=data)
        self.assertTrue(serializer.is_valid())
        self.assertDictEqual({}, serializer.errors)

    def test_slashes(self):
        overlap_errors = {"base_path": ["Relative path cannot begin or end with slashes."]}

        data = {"name": "fefe", "base_path": "fefe/"}
        serializer = DistributionSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertDictEqual(overlap_errors, serializer.errors)

        data = {"name": "fefe", "base_path": "/fefe/foo"}
        serializer = DistributionSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertDictEqual(overlap_errors, serializer.errors)

    def test_uniqueness(self):
        Distribution.objects.create(base_path="fizz/buzz", name="fizzbuzz")
        data = {"name": "feefee", "base_path": "fizz/buzz"}
        overlap_errors = {"base_path": ["This field must be unique."]}

        serializer = DistributionSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertDictEqual(overlap_errors, serializer.errors)
