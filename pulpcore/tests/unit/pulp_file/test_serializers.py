from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.conf import settings

from pulp_file.app.serializers import FileContentSerializer
from pulp_file.app.models import FileContent

from pulpcore.plugin.models import Artifact


V3_API_ROOT = (
    settings.V3_API_ROOT
    if not settings.DOMAIN_ENABLED
    else settings.V3_DOMAIN_API_ROOT.replace("<slug:pulp_domain>", "default")
)


CHECKSUM_LEN = {
    "md5": 32,
    "sha1": 40,
    "sha224": 56,
    "sha256": 64,
    "sha384": 96,
    "sha512": 128,
}


def _checksums(char):
    return {name: char * CHECKSUM_LEN[name] for name in settings.ALLOWED_CONTENT_CHECKSUMS}


class TestFileContentSerializer(TestCase):
    """Test FileContentSerializer."""

    def setUp(self):
        """Set up the FileContentSerializer tests."""
        self.artifact = Artifact.objects.create(
            size=1024,
            file=SimpleUploadedFile("test_filename", b"test content"),
            **_checksums("a"),
        )

    def test_valid_data(self):
        """Test that the FileContentSerializer accepts valid data."""
        data = {
            "artifact": f"{V3_API_ROOT}artifacts/{self.artifact.pk}/",
            "relative_path": "foo",
        }
        serializer = FileContentSerializer(data=data)
        self.assertTrue(serializer.is_valid())

    def test_absolute_path_data(self):
        """Test that the FileContentSerializer does not accept data."""
        data = {
            "artifact": f"{V3_API_ROOT}artifacts/{self.artifact.pk}/",
            "relative_path": "/foo",
        }
        serializer = FileContentSerializer(data=data)
        self.assertFalse(serializer.is_valid())

    def test_duplicate_data(self):
        """Test that the FileContentSerializer accepts duplicate valid data."""
        FileContent.objects.create(relative_path="foo", digest=self.artifact.sha256)
        data = {
            "artifact": f"{V3_API_ROOT}artifacts/{self.artifact.pk}/",
            "relative_path": "foo",
        }
        serializer = FileContentSerializer(data=data)
        self.assertTrue(serializer.is_valid())
