import os
import tempfile

from django.test import TestCase
from pulpcore.plugin.models import Artifact, Content, ContentArtifact


class ContentCRUDTestCase(TestCase):

    artifact01_path = os.path.join(tempfile.gettempdir(), 'artifact01-tmp')
    artifact02_path = os.path.join(tempfile.gettempdir(), 'artifact02-tmp')

    def setUp(self):
        with open(self.artifact01_path, 'w') as f:
            f.write('Temp Artifact File 01')
        with open(self.artifact02_path, 'w') as f:
            f.write('Temp Artifact File 02')
        self.artifact01 = Artifact.init_and_validate(self.artifact01_path)
        self.artifact01.save()
        self.artifact02 = Artifact.init_and_validate(self.artifact02_path)
        self.artifact02.save()

    def test_create_and_read_content(self):
        content = Content.objects.create()
        content.save()
        content_artifact = ContentArtifact.objects.create(
            artifact=self.artifact01,
            content=content,
            relative_path=self.artifact01.file.path)
        content_artifact.save()
        self.assertTrue(
            Content.objects.filter(pk=content.pk).exists()
            and ContentArtifact.objects.get(
                pk=content_artifact.pk
            ).content.pk == Content.objects.get(pk=content.pk).pk
        )

    def test_remove_content(self):
        content = Content.objects.create()
        content.save()
        # Assumes creation is tested by test_create_and_read_content function
        Content.objects.filter(pk=content.pk).delete()
        self.assertFalse(Content.objects.filter(pk=content.pk).exists())
