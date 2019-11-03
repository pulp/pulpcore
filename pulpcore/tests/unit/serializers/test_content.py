from unittest import TestCase

import mock
from pulpcore.app.serializers import ArtifactSerializer


class TestArtifactSerializer(TestCase):

    def test_validate_file_checksum(self):
        mock_file = mock.MagicMock(size=42)
        mock_file.hashers.__getitem__.return_value.hexdigest.return_value = 'asdf'

        data = {'file': mock_file}
        serializer = ArtifactSerializer(data=data)
        self.assertTrue(serializer.is_valid())
        new_data = serializer.validated_data
        self.assertEqual(new_data, {
            'file': mock_file,
            'size': 42,
            'md5': 'asdf',
            'sha1': 'asdf',
            'sha224': 'asdf',
            'sha256': 'asdf',
            'sha384': 'asdf',
            'sha512': 'asdf',
        })

    def test_emtpy_data(self):
        data = {}
        serializer = ArtifactSerializer(data=data)
        self.assertFalse(serializer.is_valid())
