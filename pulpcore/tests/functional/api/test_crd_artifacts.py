"""Tests that perform actions over artifacts."""
import hashlib
import itertools
import os
import uuid
import pytest

from django.conf import settings
from pulpcore.client.pulpcore import ApiException


@pytest.fixture
def pulpcore_random_file(tmp_path):
    name = tmp_path / str(uuid.uuid4())
    with open(name, "wb") as fout:
        contents = os.urandom(1024)
        fout.write(contents)
        fout.flush()
    digest = hashlib.sha256(contents).hexdigest()
    return {"name": name, "size": 1024, "digest": digest}


def _do_upload_valid_attrs(artifact_api, file, data):
    """Upload a file with the given attributes."""
    artifact = artifact_api.create(file, **data)
    # assumes ALLOWED_CONTENT_CHECKSUMS does NOT contain "md5"
    assert artifact.md5 is None, "MD5 {}".format(artifact.md5)
    read_artifact = artifact_api.read(artifact.pulp_href)
    # assumes ALLOWED_CONTENT_CHECKSUMS does NOT contain "md5"
    assert read_artifact.md5 is None
    for key, val in artifact.to_dict().items():
        assert getattr(read_artifact, key) == val
    # Delete the Artifact
    artifact_api.delete(read_artifact.pulp_href)
    with pytest.raises(ApiException) as e:
        artifact_api.read(read_artifact.pulp_href)

    assert e.value.status == 404


@pytest.mark.parallel
def test_upload_valid_attrs(artifacts_api_client, pulpcore_random_file):
    """Upload a file, and provide valid attributes.

    For each possible combination of ``sha256`` and ``size`` (including
    neither), do the following:

    1. Upload a file with the chosen combination of attributes.
    2. Verify that an artifact has been created, and that it has valid
       attributes.
    3. Delete the artifact, and verify that its attributes are
       inaccessible.
    """
    file_attrs = {"sha256": pulpcore_random_file["digest"], "size": pulpcore_random_file["size"]}
    for i in range(len(file_attrs) + 1):
        for keys in itertools.combinations(file_attrs, i):
            data = {key: file_attrs[key] for key in keys}
            _do_upload_valid_attrs(artifacts_api_client, pulpcore_random_file["name"], data)


def test_upload_empty_file(delete_orphans_pre, artifacts_api_client, tmp_path):
    """Upload an empty file.

    For each possible combination of ``sha256`` and ``size`` (including
    neither), do the following:

    1. Upload a file with the chosen combination of attributes.
    2. Verify that an artifact has been created, and that it has valid
       attributes.
    3. Delete the artifact, and verify that its attributes are
       inaccessible.
    """
    file = tmp_path / str(uuid.uuid4())
    file.touch()
    empty_file = b""
    file_attrs = {"sha256": hashlib.sha256(empty_file).hexdigest(), "size": 0}
    for i in range(len(file_attrs) + 1):
        for keys in itertools.combinations(file_attrs, i):
            data = {key: file_attrs[key] for key in keys}
            _do_upload_valid_attrs(artifacts_api_client, file, data)


@pytest.mark.parallel
def test_upload_invalid_attrs(artifacts_api_client, pulpcore_random_file):
    """Upload a file, and provide invalid attributes.

    For each possible combination of ``sha256`` and ``size`` (except for
    neither), do the following:

    1. Upload a file with the chosen combination of attributes. Verify that
       an error is returned.
    2. Verify that no artifacts exist in Pulp whose attributes match the
       file that was unsuccessfully uploaded.
    """
    file_attrs = {"sha256": str(uuid.uuid4()), "size": pulpcore_random_file["size"] + 1}
    for i in range(1, len(file_attrs) + 1):
        for keys in itertools.combinations(file_attrs, i):
            data = {key: file_attrs[key] for key in keys}
            _do_upload_invalid_attrs(artifacts_api_client, pulpcore_random_file, data)


def _do_upload_invalid_attrs(artifact_api, file, data):
    """Upload a file with the given attributes."""
    with pytest.raises(ApiException) as e:
        artifact_api.create(file["name"], **data)

    assert e.value.status == 400
    artifacts = artifact_api.list()
    for artifact in artifacts.results:
        assert artifact.sha256 != file["digest"]


@pytest.mark.parallel
def test_upload_md5(artifacts_api_client, pulpcore_random_file):
    """Attempt to upload a file using an MD5 checksum.

    Assumes ALLOWED_CONTENT_CHECKSUMS does NOT contain ``md5``
    """
    file_attrs = {"md5": str(uuid.uuid4()), "size": pulpcore_random_file["size"]}
    with pytest.raises(ApiException) as e:
        artifacts_api_client.create(pulpcore_random_file["name"], **file_attrs)

    assert e.value.status == 400


@pytest.mark.parallel
def test_upload_mixed_attrs(artifacts_api_client, pulpcore_random_file):
    """Upload a file, and provide both valid and invalid attributes.

    Do the following:

    1. Upload a file and provide both an ``sha256`` and a ``size``. Let one
       be valid, and the other be invalid. Verify that an error is returned.
    2. Verify that no artifacts exist in Pulp whose attributes match the
       file that was unsuccessfully uploaded.
    """
    invalid_data = (
        {"sha256": pulpcore_random_file["digest"], "size": pulpcore_random_file["size"] + 1},
        {"sha256": str(uuid.uuid4()), "size": pulpcore_random_file["size"]},
    )
    for data in invalid_data:
        _do_upload_invalid_attrs(artifacts_api_client, pulpcore_random_file, data)


@pytest.mark.parallel
def test_delete_artifact(artifacts_api_client, pulpcore_random_file):
    """Delete an artifact, it is removed from the filesystem."""
    if settings.DEFAULT_FILE_STORAGE != "pulpcore.app.models.storage.FileSystem":
        pytest.skip("this test only works for filesystem storage")
    media_root = settings.MEDIA_ROOT

    artifact = artifacts_api_client.create(pulpcore_random_file["name"])
    path_to_file = os.path.join(media_root, artifact.file)
    file_exists = os.path.exists(path_to_file)
    assert file_exists

    # delete
    artifacts_api_client.delete(artifact.pulp_href)
    file_exists = os.path.exists(path_to_file)
    assert not file_exists
