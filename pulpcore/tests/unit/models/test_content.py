import os
import tempfile
from unittest import mock

from django.core.files.storage import default_storage as storage
from django.core.files.uploadedfile import SimpleUploadedFile

from django.conf import settings
from django.test import SimpleTestCase, TestCase
from pulpcore.plugin.exceptions import (
    UnsupportedDigestValidationError,
    MissingDigestValidationError,
)

from pulpcore.plugin.models import (
    Artifact,
    Content,
    ContentArtifact,
    PulpTemporaryFile,
    Remote,
    RemoteArtifact,
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
        name = temp_file.file.file.name
        assert name.startswith("/var/lib/pulp/media/tmp/files"), name

    def test_read_temp_file(self):
        with tempfile.NamedTemporaryFile("ab") as tf:
            tf.write(b"temp file test")
            tf.flush()
            temp_file = PulpTemporaryFile(file=tf.name)
            temp_file.save()

        assert b"temp file test" in temp_file.file.read()


class ArtifactAlgorithmTestCase(SimpleTestCase):
    @mock.patch(
        "pulpcore.app.models.Artifact.FORBIDDEN_DIGESTS",
        new_callable=mock.PropertyMock,
        return_value=set(["md5"]),
    )
    @mock.patch(
        "pulpcore.app.models.Artifact.DIGEST_FIELDS",
        new_callable=mock.PropertyMock,
        return_value=set(["sha512", "sha384", "sha224", "sha1", "sha256"]),
    )
    def test_direct_set_forbidden(self, mock_FORBIDDEN_DIGESTS, mock_DIGEST_FIELDS):
        with self.assertRaises(UnsupportedDigestValidationError):
            a = Artifact(
                file=SimpleUploadedFile("test_filename", b"test content"),
                sha512="asdf",
                sha384="asdf",
                sha224="asdf",
                sha1="asdf",
                sha256="asdf",
                size=1024,
            )
            a.md5 = "asdf"
            a.save()

    @mock.patch(
        "pulpcore.app.models.Artifact.FORBIDDEN_DIGESTS",
        new_callable=mock.PropertyMock,
        return_value=set(["md5"]),
    )
    @mock.patch(
        "pulpcore.app.models.Artifact.DIGEST_FIELDS",
        new_callable=mock.PropertyMock,
        return_value=set(["sha512", "sha384", "sha224", "sha1", "sha256"]),
    )
    def test_forgot_something(self, mock_FORBIDDEN_DIGESTS, mock_DIGEST_FIELDS):
        with self.assertRaises(MissingDigestValidationError):
            a = Artifact(
                file=SimpleUploadedFile("test_filename", b"test content"),
                sha512="asdf",
                sha384="asdf",
                sha224="asdf",
                sha1="asdf",
                sha256="asdf",
                size=1024,
            )
            a.sha224 = None
            a.save()


class TestRemoteArtifact(TestCase):
    def setUp(self):
        self.content = Content.objects.create(pulp_type="core.content")
        self.ca = ContentArtifact.objects.create(content=self.content)
        self.remote = Remote.objects.create(name="pulp", url="www.pulpproject.org")

    @mock.patch(
        "pulpcore.app.models.content.DigestModel.FORBIDDEN_DIGESTS",
        new_callable=mock.PropertyMock,
        return_value=set(["md5", "sha1"]),
    )
    def test_allowed_checksums(self, mock_FORBIDDEN_DIGESTS):
        remote_artifact = RemoteArtifact(
            content_artifact=self.ca,
            remote=self.remote,
            sha256="b94d27b9934d3e08a52e52d7da7dabfac484efe37a5380ee9088f7ace2efcde9",
        )
        remote_artifact.save()

    @mock.patch(
        "pulpcore.app.models.content.DigestModel.FORBIDDEN_DIGESTS",
        new_callable=mock.PropertyMock,
        return_value=set(["md5", "sha1"]),
    )
    def test_forbidden_checksums(self, mock_FORBIDDEN_DIGESTS):
        with self.assertRaises(UnsupportedDigestValidationError):
            RemoteArtifact(
                content_artifact=self.ca, remote=self.remote, md5="5eb63bbbe01eeed093cb22bb8f5acdc3"
            )
        with self.assertRaises(UnsupportedDigestValidationError):
            RemoteArtifact(
                content_artifact=self.ca,
                remote=self.remote,
                md5="5eb63bbbe01eeed093cb22bb8f5acdc3",
                sha256="b94d27b9934d3e08a52e52d7da7dabfac484efe37a5380ee9088f7ace2efcde9",
            )
