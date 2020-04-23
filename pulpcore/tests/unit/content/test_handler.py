from unittest.mock import Mock

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase

from pulpcore.content import Handler
from pulpcore.plugin.models import Artifact, Content, ContentArtifact


class HandlerSaveContentTestCase(TestCase):
    def setUp(self):
        self.c1 = Content.objects.create()
        self.ca1 = ContentArtifact.objects.create(
            artifact=None, content=self.c1, relative_path="c1"
        )
        self.ra1 = Mock(content_artifact=self.ca1)
        self.c2 = Content.objects.create()
        self.ca2 = ContentArtifact.objects.create(
            artifact=None, content=self.c2, relative_path="c2"
        )
        self.ra2 = Mock(content_artifact=self.ca2)

    def download_result_mock(self, path):
        dr = Mock()
        dr.artifact_attributes = {"size": 0}
        for digest_type in Artifact.DIGEST_FIELDS:
            dr.artifact_attributes[digest_type] = "abc123"
        dr.path = SimpleUploadedFile(name=path, content="")
        return dr

    def test_save_artifact(self):
        """Artifact needs to be created."""
        cch = Handler()
        new_artifact = cch._save_artifact(self.download_result_mock("c1"), self.ra1)
        c1 = Content.objects.get(pk=self.c1.pk)
        self.assertIsNotNone(new_artifact)
        self.assertEqual(c1._artifacts.get().pk, new_artifact.pk)

    def test_save_artifact_artifact_already_exists(self):
        """Artifact turns out to already exist."""
        cch = Handler()
        new_artifact = cch._save_artifact(self.download_result_mock("c1"), self.ra1)

        existing_artifact = cch._save_artifact(self.download_result_mock("c2"), self.ra2)
        c2 = Content.objects.get(pk=self.c2.pk)
        self.assertEqual(existing_artifact.pk, new_artifact.pk)
        self.assertEqual(c2._artifacts.get().pk, existing_artifact.pk)
