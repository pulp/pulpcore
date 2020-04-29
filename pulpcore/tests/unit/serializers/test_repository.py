from unittest import TestCase

import mock
from rest_framework import serializers

from pulpcore.app.models import BaseDistribution
from pulpcore.app.serializers import BaseDistributionSerializer, PublicationSerializer


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
        BaseDistribution.objects.create(base_path="foo/bar", name="foobar")
        overlap_errors = {"base_path": ["Overlaps with existing distribution 'foobar'"]}

        # test that the new distribution cannot be nested in an existing path
        data = {"name": "foobarbaz", "base_path": "foo/bar/baz"}
        serializer = BaseDistributionSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertDictEqual(overlap_errors, serializer.errors)

        # test that the new distribution cannot nest an existing path
        data = {"name": "foo", "base_path": "foo"}
        serializer = BaseDistributionSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertDictEqual(overlap_errors, serializer.errors)

    def test_no_overlap(self):
        BaseDistribution.objects.create(base_path="fu/bar", name="fubar")

        # different path
        data = {"name": "fufu", "base_path": "fubar"}
        serializer = BaseDistributionSerializer(data=data)
        self.assertTrue(serializer.is_valid())
        self.assertDictEqual({}, serializer.errors)

        # common base path but different path
        data = {"name": "fufu", "base_path": "fu/baz"}
        serializer = BaseDistributionSerializer(data=data)
        self.assertTrue(serializer.is_valid())
        self.assertDictEqual({}, serializer.errors)

    def test_slashes(self):
        overlap_errors = {"base_path": ["Relative path cannot begin or end with slashes."]}

        data = {"name": "fefe", "base_path": "fefe/"}
        serializer = BaseDistributionSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertDictEqual(overlap_errors, serializer.errors)

        data = {"name": "fefe", "base_path": "/fefe/foo"}
        serializer = BaseDistributionSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertDictEqual(overlap_errors, serializer.errors)

    def test_uniqueness(self):
        BaseDistribution.objects.create(base_path="fizz/buzz", name="fizzbuzz")
        data = {"name": "feefee", "base_path": "fizz/buzz"}
        overlap_errors = {"base_path": ["This field must be unique."]}

        serializer = BaseDistributionSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertDictEqual(overlap_errors, serializer.errors)
