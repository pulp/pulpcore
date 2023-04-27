import pytest
from collections import namedtuple

from django.core.files.storage import default_storage as storage
from django.core.files.uploadedfile import SimpleUploadedFile

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


@pytest.mark.django_db
def test_create_read_delete_content(tmp_path):
    artifact_path = tmp_path / "artifact-tmp"
    artifact_path.write_text("Temp Artifact File")
    artifact = Artifact.init_and_validate(str(artifact_path))
    artifact.save()

    content = Content.objects.create()
    artifact_file = storage.open(artifact.file.name)
    content_artifact = ContentArtifact.objects.create(
        artifact=artifact, content=content, relative_path=artifact_file.name
    )
    assert Content.objects.filter(pk=content.pk).exists()
    assert (
        ContentArtifact.objects.get(pk=content_artifact.pk).content.pk
        == Content.objects.get(pk=content.pk).pk
    )

    Content.objects.filter(pk=content.pk).delete()
    assert not Content.objects.filter(pk=content.pk).exists()


@pytest.mark.django_db
def test_storage_location(tmp_path, settings):
    if settings.DEFAULT_FILE_STORAGE != "pulpcore.app.models.storage.FileSystem":
        pytest.skip("Skipping test for nonlocal storage.")

    tf = tmp_path / "ab"
    tf.write_bytes(b"temp file test")
    temp_file = PulpTemporaryFile(file=str(tf))
    temp_file.save()

    assert temp_file.file.name.startswith("tmp/files/")
    name = temp_file.file.file.name
    assert name.startswith("/var/lib/pulp/media/tmp/files"), name


@pytest.mark.django_db
def test_read_temp_file(tmp_path):
    tf = tmp_path / "ab"
    tf.write_bytes(b"temp file test")
    temp_file = PulpTemporaryFile(file=str(tf))
    temp_file.save()

    assert b"temp file test" in temp_file.file.read()


@pytest.mark.django_db
def test_artifact_forbidden_digest(monkeypatch):
    monkeypatch.setattr(Artifact, "FORBIDDEN_DIGESTS", {"md5"})
    monkeypatch.setattr(Artifact, "DIGEST_FIELDS", {"sha512", "sha384", "sha224", "sha1", "sha256"})

    with pytest.raises(UnsupportedDigestValidationError):
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


@pytest.mark.django_db
def test_artifact_forgotten_digest(monkeypatch):
    monkeypatch.setattr(Artifact, "FORBIDDEN_DIGESTS", {"md5"})
    monkeypatch.setattr(Artifact, "DIGEST_FIELDS", {"sha512", "sha384", "sha224", "sha1", "sha256"})
    with pytest.raises(MissingDigestValidationError):
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


@pytest.fixture
def remote_artifact_setup(monkeypatch, db):
    monkeypatch.setattr(Artifact, "FORBIDDEN_DIGESTS", {"md5", "sha1"})
    monkeypatch.setattr(Artifact, "DIGEST_FIELDS", {"sha512", "sha384", "sha224", "sha256"})

    content = Content.objects.create()
    content_artifact = ContentArtifact.objects.create(
        artifact=None, content=content, relative_path="ca"
    )
    remote = Remote.objects.create(url="http://example.org/")
    return namedtuple("RemoteArtifactSetup", "content content_artifact remote")(
        content, content_artifact, remote
    )


def test_remoteartifact_with_no_checksums(remote_artifact_setup):
    ra = RemoteArtifact(
        url="http://example.org/file",
        size=1024,
        md5=None,
        sha1=None,
        sha224=None,
        sha256="",
        sha384=None,
        sha512=None,
        content_artifact=remote_artifact_setup.content_artifact,
        remote=remote_artifact_setup.remote,
    )
    ra.validate_checksums()


def test_remoteartifact_with_allowed_checksums(remote_artifact_setup):
    ra = RemoteArtifact(
        url="http://example.org/file",
        size=1024,
        md5="",
        sha1=None,
        sha224=None,
        sha256="sha256checksum",
        sha384=None,
        sha512=None,
        content_artifact=remote_artifact_setup.content_artifact,
        remote=remote_artifact_setup.remote,
    )
    ra.validate_checksums()


def test_remoteartifact_with_allowed_and_forbidden_checksums(remote_artifact_setup):
    ra = RemoteArtifact(
        url="http://example.org/file",
        size=1024,
        md5="",
        sha1="sha1checksum",
        sha224=None,
        sha256="sha256checksum",
        sha384=None,
        sha512=None,
        content_artifact=remote_artifact_setup.content_artifact,
        remote=remote_artifact_setup.remote,
    )
    ra.validate_checksums()


def test_remoteartifact_with_forbidden_checksums(remote_artifact_setup):
    with pytest.raises(UnsupportedDigestValidationError):
        ra = RemoteArtifact(
            url="http://example.org/file",
            size=1024,
            md5="md5checksum",
            sha1=None,
            sha224=None,
            sha256="",
            sha384=None,
            sha512=None,
            content_artifact=remote_artifact_setup.content_artifact,
            remote=remote_artifact_setup.remote,
        )
        ra.validate_checksums()
