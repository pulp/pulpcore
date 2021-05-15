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
        data = {"full": True, "dry_run": False, "output_file_info": {"bar": "blech"}}
        serializer = PulpExportSerializer(data=data)
        self.assertTrue(serializer.is_valid())

        with self.assertRaises(AttributeError):
            serializer.output_file_info["bar"]

    def test_chunk_size(self):
        # positive tests
        # bytes
        data = {"chunk_size": "100B"}
        serializer = PulpExportSerializer(data=data)
        self.assertTrue(serializer.is_valid())
        self.assertEqual(100, serializer.validated_data["chunk_size"])

        # kilobytes
        data = {"chunk_size": "100KB"}
        serializer = PulpExportSerializer(data=data)
        self.assertTrue(serializer.is_valid())
        self.assertEqual(100 * 1024, serializer.validated_data["chunk_size"])

        # megabytes
        data = {"chunk_size": "100MB"}
        serializer = PulpExportSerializer(data=data)
        self.assertTrue(serializer.is_valid())
        self.assertEqual(100 * 1024 * 1024, serializer.validated_data["chunk_size"])

        # gigabytes
        data = {"chunk_size": "100GB"}
        serializer = PulpExportSerializer(data=data)
        self.assertTrue(serializer.is_valid())
        self.assertEqual(100 * 1024 * 1024 * 1024, serializer.validated_data["chunk_size"])

        # terabytes
        data = {"chunk_size": "1TB"}
        serializer = PulpExportSerializer(data=data)
        self.assertTrue(serializer.is_valid())
        self.assertEqual(1 * 1024 * 1024 * 1024 * 1024, serializer.validated_data["chunk_size"])

        # float-units
        data = {"chunk_size": "2.4GB"}
        serializer = PulpExportSerializer(data=data)
        self.assertTrue(serializer.is_valid())
        self.assertEqual(int(2.4 * 1024 * 1024 * 1024), serializer.validated_data["chunk_size"])

        # negative tests
        # no units
        data = {"chunk_size": "100"}
        serializer = PulpExportSerializer(data=data)
        self.assertFalse(serializer.is_valid())

        # not-a-number
        data = {"chunk_size": "bazMB"}
        serializer = PulpExportSerializer(data=data)
        serializer.is_valid()

        # non-positive
        data = {"chunk_size": "0GB"}
        serializer = PulpExportSerializer(data=data)
        self.assertFalse(serializer.is_valid())

        # non-positive
        data = {"chunk_size": "-10KB"}
        serializer = PulpExportSerializer(data=data)
        self.assertFalse(serializer.is_valid())

        # too many terabytes
        data = {"chunk_size": "100TB"}
        serializer = PulpExportSerializer(data=data)
        self.assertFalse(serializer.is_valid())

        # morbidly many megabytes
        data = {"chunk_size": "10000000000000M"}
        serializer = PulpExportSerializer(data=data)
        self.assertFalse(serializer.is_valid())
