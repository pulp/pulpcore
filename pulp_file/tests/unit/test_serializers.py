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


class TestFileContentSerializer(TestCase):
    """Test FileContentSerializer."""

    def setUp(self):
        """Set up the FileContentSerializer tests."""
        self.artifact = Artifact.objects.create(
            sha1="cf6121b0425c2f2e3a2fcfe6f402d59730eb5661",
            sha224="9a6297eb28d91fad5277c0833856031d0e940432ad807658bd2b60f4",
            sha256="c8ddb3dcf8da48278d57b0b94486832c66a8835316ccf7ca39e143cbfeb9184f",
            sha384="53a8a0cebcb7780ed7624790c9d9a4d09ba74b47270d397f5ed7bc1c46777a0fbe362aaf2bbe7f0966a350a12d76e28d",  # noqa
            sha512="a94a65f19b864d184a2a5e07fa29766f08c6d49b6f624b3dd3a36a98267b9137d9c35040b3e105448a869c23c2aec04c9e064e3555295c1b8de6515eed4da27d",  # noqa
            size=1024,
            file=SimpleUploadedFile("test_filename", b"test content"),
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
