import hashlib

import pytest
from django.core.files import File
from django.core.files.uploadedfile import SimpleUploadedFile

from pulpcore.app.models import Artifact, Domain
from pulpcore.app.models.storage import FileSystem


@pytest.fixture
def artifact_storage_root(monkeypatch, tmp_path):
    storage_root = tmp_path / "media"
    storage = FileSystem(location=str(storage_root))
    monkeypatch.setattr(Domain, "get_storage", lambda self: storage)
    return storage_root


@pytest.mark.django_db
def test_artifact_upload_with_empty_media_root(settings, artifact_storage_root):
    settings.MEDIA_ROOT = ""

    contents = b"artifact upload"
    artifact = Artifact.objects.create(
        file=SimpleUploadedFile("artifact-upload.txt", contents),
        size=len(contents),
        **{digest: hashlib.new(digest, contents).hexdigest() for digest in Artifact.DIGEST_FIELDS},
    )

    artifact.refresh_from_db()
    assert artifact.file.read() == contents


@pytest.mark.django_db
def test_artifact_file_object_from_artifact_storage_is_rejected(artifact_storage_root):
    contents = b"artifact already in storage"
    source_path = artifact_storage_root / "artifact" / "other"
    source_path.parent.mkdir(parents=True)
    source_path.write_bytes(contents)
    digests = {
        digest: hashlib.new(digest, contents).hexdigest() for digest in Artifact.DIGEST_FIELDS
    }

    with source_path.open("rb") as source:
        artifact = Artifact(file=File(source), size=len(contents), **digests)
        with pytest.raises(ValueError, match="already present in Artifact storage"):
            artifact.save()
