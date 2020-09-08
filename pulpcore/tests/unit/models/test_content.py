import os
import tempfile

from django.core.files.storage import default_storage as storage
from django.conf import settings
from django.test import TestCase
from pulpcore.plugin.models import (
    Artifact,
    Content,
    ContentArtifact,
    PulpTemporaryFile,
    UnsupportedDigestValidationError,
)


class ContentCRUDTestCase(TestCase):

    artifact01_path = os.path.join(tempfile.gettempdir(), "artifact01-tmp")
    artifact02_path = os.path.join(tempfile.gettempdir(), "artifact02-tmp")

    def setUp(self):
        with open(self.artifact01_path, "w") as f:
            f.write("Temp Artifact File 01")
        with open(self.artifact02_path, "w") as f:
            f.write("Temp Artifact File 02")
        self.artifact01 = Artifact.init_and_validate(self.artifact01_path)
        self.artifact01.save()
        self.artifact02 = Artifact.init_and_validate(self.artifact02_path)
        self.artifact02.save()

    def test_create_and_read_content(self):
        content = Content.objects.create()
        content.save()
        artifact_file = storage.open(self.artifact01.file.name)
        content_artifact = ContentArtifact.objects.create(
            artifact=self.artifact01, content=content, relative_path=artifact_file.name
        )
        content_artifact.save()
        self.assertTrue(
            Content.objects.filter(pk=content.pk).exists()
            and ContentArtifact.objects.get(pk=content_artifact.pk).content.pk
            == Content.objects.get(pk=content.pk).pk
        )

    def test_remove_content(self):
        content = Content.objects.create()
        content.save()
        # Assumes creation is tested by test_create_and_read_content function
        Content.objects.filter(pk=content.pk).delete()
        self.assertFalse(Content.objects.filter(pk=content.pk).exists())


class PulpTemporaryFileTestCase(TestCase):
    def test_storage_location(self):
        if settings.DEFAULT_FILE_STORAGE != "pulpcore.app.models.storage.FileSystem":
            self.skipTest("Skipping test for nonlocal storage.")

        with tempfile.NamedTemporaryFile("ab") as tf:
            temp_file = PulpTemporaryFile(file=tf.name)
            temp_file.save()

        assert temp_file.file.name.startswith("tmp/files/")
        assert temp_file.file.file.name.startswith("/var/lib/pulp/tmp/files")

    def test_read_temp_file(self):
        with tempfile.NamedTemporaryFile("ab") as tf:
            tf.write(b"temp file test")
            tf.flush()
            temp_file = PulpTemporaryFile(file=tf.name)
            temp_file.save()

        assert b"temp file test" in temp_file.file.read()


class ArtifactAlgorithmTestCase(TestCase):
    def test_set_forbidden(self):
        # This will only fire on a Pulp instance that has forbidden md5 in settings.py
        if "md5" not in Artifact.DIGEST_FIELDS:
            with self.assertRaises(UnsupportedDigestValidationError) as udv:  # noqa
                a = Artifact(md5="asdf")  # noqa
        else:
            pass
