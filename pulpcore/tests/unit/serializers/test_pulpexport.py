from unittest import TestCase

from pulpcore.app.serializers import PulpExportSerializer


class TestPulpExportSerializer(TestCase):
    def test_validate_no_params(self):
        data = {}
        serializer = PulpExportSerializer(data=data)
        self.assertTrue(serializer.is_valid())

    def test_validate_bad_param_values(self):
        data = {"full": "bar", "dry_run": 0}
        serializer = PulpExportSerializer(data=data)
        self.assertFalse(serializer.is_valid())

    def test_bad_params(self):
        data = {"baz": "bar"}
        serializer = PulpExportSerializer(data=data)
        self.assertFalse(serializer.is_valid())

    def test_read_only_params(self):
        data = {"full": True, "dry_run": False, "sha256": "bar", "filename": "blech"}
        serializer = PulpExportSerializer(data=data)

        with self.assertRaises(AttributeError):
            serializer.sha256

        with self.assertRaises(AttributeError):
            serializer.filename

        with self.assertRaises(AttributeError):
            serializer.sha256
