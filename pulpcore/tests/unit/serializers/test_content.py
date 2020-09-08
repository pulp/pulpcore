from unittest import TestCase

import mock
from pulpcore.app.models import Artifact
from pulpcore.app.serializers import ArtifactSerializer
from pulpcore.constants import ALL_KNOWN_CONTENT_CHECKSUMS
from rest_framework import serializers


class TestArtifactSerializer(TestCase):
    def test_validate_file_checksum(self):
        mock_file = mock.MagicMock(size=42)
        mock_file.hashers.__getitem__.return_value.hexdigest.return_value = "asdf"

        data = {"file": mock_file}
        serializer = ArtifactSerializer(data=data)
        self.assertTrue(serializer.is_valid())
        new_data = serializer.validated_data
        self.assertEqual(new_data["file"], mock_file)
        self.assertEqual(new_data["size"], 42)
        for csum in Artifact.DIGEST_FIELDS:
            self.assertEqual(new_data[csum], "asdf")

        for csum in ALL_KNOWN_CONTENT_CHECKSUMS.difference(Artifact.DIGEST_FIELDS):
            self.assertFalse(csum in new_data, f"Found forbidden checksum {csum}")

        # This part of the test will only fire if the system-under-test has forbidden
        # use of 'md5'
        if "md5" not in Artifact.DIGEST_FIELDS:
            data = {"file": mock_file, "md5": "asdf"}
            with self.assertRaises(serializers.ValidationError) as cm:  # noqa
                serializer.validate(data)

    def test_emtpy_data(self):
        data = {}
        serializer = ArtifactSerializer(data=data)
        self.assertFalse(serializer.is_valid())
