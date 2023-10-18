from django.core.files.storage import default_storage as storage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from pulpcore.plugin.models import Artifact, ContentArtifact, RepositoryVersion
from pulpcore.app.models.task import Task

from pulp_file.app.models import FileContent, FileRepository


class RepositoryVersionCRUDTestCase(TestCase):
    """Test RepositoryVersion CRUD and content association."""

    def setUp(self):
        """Create Artifact, Content, ContentArtifact, and Repository."""
        artifact = Artifact.objects.create(
            sha1="cf6121b0425c2f2e3a2fcfe6f402d59730eb5661",
            sha224="9a6297eb28d91fad5277c0833856031d0e940432ad807658bd2b60f4",
            sha256="c8ddb3dcf8da48278d57b0b94486832c66a8835316ccf7ca39e143cbfeb9184f",
            sha384=(
                "53a8a0cebcb7780ed7624790c9d9a4d09ba74b47270d397f5ed7bc1c46777a0f"
                "be362aaf2bbe7f0966a350a12d76e28d"
            ),
            # noqa
            sha512=(
                "a94a65f19b864d184a2a5e07fa29766f08c6d49b6f624b3dd3a36a9826"
                "7b9137d9c35040b3e105448a869c23c2aec04c9e064e3555295c1b8de6515eed4da27d"
            ),
            # noqa
            size=1024,
            file=SimpleUploadedFile("test_filename", b"test content"),
        )
        artifact.save()
        self.content = FileContent.objects.create()
        self.content.save()
        artifact_file = storage.open(artifact.file.name)
        self.content_artifact = ContentArtifact.objects.create(
            artifact=artifact, content=self.content, relative_path=artifact_file.name
        )
        self.content_artifact.save()
        self.repository = FileRepository.objects.create(name="foo")
        self.repository.save()
        self.task = Task.objects.create(state="Completed", name="test-task")
        self.task.save()

    def test_create_repository_version(self):
        """Test creating a RepositoryVersion."""
        with self.repository.new_version() as new_version:
            new_version.add_content(FileContent.objects.filter(pk=self.content.pk))
        self.assertTrue(RepositoryVersion.objects.filter().exists())

    def test_remove_repository_version(self):
        """Test deleting a RepositoryVersion."""
        RepositoryVersion.objects.filter().delete()
        self.assertFalse(RepositoryVersion.objects.filter().exists())
