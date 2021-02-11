from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from dynaconf import settings

from pulpcore.app.checks import (
    artifact_checksum_check,
    checksum_setting_check,
    content_origin_check,
)
from pulpcore.app.models import Artifact


class ContentOriginCase(TestCase):
    @override_settings()
    def test_no_sha256(self):
        del settings.CONTENT_ORIGIN
        errors = content_origin_check([])
        self.assertEqual(1, len(errors))
        self.assertEqual("pulpcore.E001", errors[0].id)


class ContentChecksumCase(TestCase):
    @override_settings(ALLOWED_CONTENT_CHECKSUMS={"sha512"})
    def test_no_sha256(self):
        errors = checksum_setting_check([])
        self.assertEqual(1, len(errors))
        self.assertEqual("pulpcore.E002", errors[0].id)

    @override_settings(ALLOWED_CONTENT_CHECKSUMS={"sha256", "rot13"})
    def test_unknown_algorithm(self):
        errors = checksum_setting_check([])
        self.assertEqual(1, len(errors))
        self.assertEqual("pulpcore.E003", errors[0].id)


class ArtifactChecksumCase(TestCase):
    @staticmethod
    def _create_artifact(**kwargs):
        kwargs["file"] = SimpleUploadedFile("test_filename", b"hello world")
        kwargs["size"] = "12"
        artifact = Artifact(**kwargs)
        artifact.save(skip_hooks=True)

    @override_settings(ALLOWED_CONTENT_CHECKSUMS={"sha256", "sha512"})
    def test_missing_artifact_checksum(self):
        self._create_artifact(
            sha256="b94d27b9934d3e08a52e52d7da7dabfac484efe37a5380ee9088f7ace2efcde9"
        )
        errors = artifact_checksum_check([])
        self.assertEqual(1, len(errors))
        self.assertEqual("pulpcore.E004", errors[0].id)

    @override_settings(ALLOWED_CONTENT_CHECKSUMS={"sha256"})
    def test_prohibited_artifact_checksum(self):
        self._create_artifact(
            sha256="b94d27b9934d3e08a52e52d7da7dabfac484efe37a5380ee9088f7ace2efcde9",
            md5="6f5902ac237024bdd0c176cb93063dc4",
        )
        errors = artifact_checksum_check([])
        self.assertEqual(1, len(errors))
        self.assertEqual("pulpcore.E005", errors[0].id)
