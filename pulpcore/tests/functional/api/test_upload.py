"""Tests related to content upload."""

import hashlib
import uuid
import pytest
import os

from random import shuffle
from pulpcore.client.pulpcore import ApiException


@pytest.fixture
def pulpcore_random_chunked_file_factory(tmp_path):
    """Returns a function to create random chunks to be uploaded."""

    def _create_chunks(number_chunks=2, chunk_sizes=None):
        # Default to 512 byte chunk sizes
        if chunk_sizes:
            if len(chunk_sizes) != number_chunks:
                raise Exception("number_chunks != len(chunk_sizes)")
        else:
            chunk_sizes = [512] * number_chunks
        chunks = {"size": sum(chunk_sizes), "chunks": []}
        hasher = hashlib.new("sha256")
        start = 0
        for chunk_size in chunk_sizes:
            name = tmp_path / str(uuid.uuid4())
            with open(name, "wb") as f:
                content = os.urandom(chunk_size)
                hasher.update(content)
                f.write(content)
                f.flush()
            content_sha = hashlib.sha256(content).hexdigest()
            end = start + chunk_size - 1
            chunks["chunks"].append((name, f"bytes {start}-{end}/{chunks['size']}", content_sha))
            start = start + chunk_size
        chunks["digest"] = hasher.hexdigest()
        return chunks

    return _create_chunks


@pytest.fixture
def pulpcore_upload_chunks(
    pulpcore_bindings,
    gen_object_with_cleanup,
    monitor_task,
):
    """Upload file in chunks."""
    artifacts = []

    def _upload_chunks(size, chunks, sha256, include_chunk_sha256=False):
        """
        Chunks is a list of tuples in the form of (chunk_filename, "bytes-ranges", optional_sha256).
        """
        upload = gen_object_with_cleanup(pulpcore_bindings.UploadsApi, {"size": size})

        for data in chunks:
            kwargs = {"file": data[0], "content_range": data[1], "upload_href": upload.pulp_href}
            if include_chunk_sha256:
                if len(data) != 3:
                    raise Exception(f"Chunk didn't include its sha256: {data}")
                kwargs["sha256"] = data[2]

            pulpcore_bindings.UploadsApi.update(**kwargs)

        finish_task = pulpcore_bindings.UploadsApi.commit(upload.pulp_href, {"sha256": sha256}).task
        response = monitor_task(finish_task)
        artifact_href = response.created_resources[0]
        artifact = pulpcore_bindings.ArtifactsApi.read(artifact_href)
        artifacts.append(artifact_href)
        return upload, artifact

    yield _upload_chunks


@pytest.mark.parallel
def test_create_artifact_without_checksum(
    pulpcore_upload_chunks, pulpcore_random_chunked_file_factory
):
    """Test creation of artifact using upload of files in chunks."""

    file_chunks_data = pulpcore_random_chunked_file_factory()
    size = file_chunks_data["size"]
    chunks = file_chunks_data["chunks"]
    shuffle(chunks)
    sha256 = file_chunks_data["digest"]

    _, artifact = pulpcore_upload_chunks(size, chunks, sha256)

    assert artifact.sha256 == sha256


@pytest.mark.parallel
def test_create_artifact_passing_checksum(
    pulpcore_upload_chunks, pulpcore_random_chunked_file_factory
):
    """Test creation of artifact using upload of files in chunks passing checksum."""
    file_chunks_data = pulpcore_random_chunked_file_factory(number_chunks=5)
    size = file_chunks_data["size"]
    chunks = file_chunks_data["chunks"]
    shuffle(chunks)
    sha256 = file_chunks_data["digest"]

    _, artifact = pulpcore_upload_chunks(size, chunks, sha256, include_chunk_sha256=True)

    assert artifact.sha256 == sha256


@pytest.mark.parallel
def test_upload_chunk_wrong_checksum(
    pulpcore_bindings, pulpcore_random_chunked_file_factory, gen_object_with_cleanup
):
    """Test creation of artifact using upload of files in chunks passing wrong checksum."""
    file_chunks_data = pulpcore_random_chunked_file_factory()
    size = file_chunks_data["size"]
    chunks = file_chunks_data["chunks"]

    upload = gen_object_with_cleanup(pulpcore_bindings.UploadsApi, {"size": size})
    for data in chunks:
        kwargs = {"file": data[0], "content_range": data[1], "upload_href": upload.pulp_href}
        kwargs["sha256"] = "WRONG CHECKSUM"
        with pytest.raises(ApiException) as e:
            pulpcore_bindings.UploadsApi.update(**kwargs)

        assert e.value.status == 400


@pytest.mark.parallel
def test_upload_response(
    pulpcore_bindings, pulpcore_random_chunked_file_factory, gen_object_with_cleanup
):
    """Test upload responses when creating an upload and uploading chunks."""
    file_chunks_data = pulpcore_random_chunked_file_factory(chunk_sizes=[6291456, 4194304])
    upload = gen_object_with_cleanup(
        pulpcore_bindings.UploadsApi, {"size": file_chunks_data["size"]}
    )

    expected_keys = ["pulp_href", "pulp_created", "size"]
    for key in expected_keys:
        assert getattr(upload, key)

    for data in file_chunks_data["chunks"]:
        kwargs = {"file": data[0], "content_range": data[1], "upload_href": upload.pulp_href}
        response = pulpcore_bindings.UploadsApi.update(**kwargs)

        for key in expected_keys:
            assert getattr(response, key)

    upload = pulpcore_bindings.UploadsApi.read(upload.pulp_href)

    expected_keys.append("chunks")

    for key in expected_keys:
        assert getattr(upload, key)

    expected_chunks = [
        {"offset": 0, "size": 6291456},
        {"offset": 6291456, "size": 4194304},
    ]

    sorted_chunks_response = sorted([c.to_dict() for c in upload.chunks], key=lambda i: i["offset"])
    assert sorted_chunks_response == expected_chunks


@pytest.mark.parallel
def test_delete_upload(
    pulpcore_bindings, pulpcore_upload_chunks, pulpcore_random_chunked_file_factory
):
    """Check whether uploads are being correctly deleted after committing."""
    file_chunks_data = pulpcore_random_chunked_file_factory()
    size = file_chunks_data["size"]
    chunks = file_chunks_data["chunks"]
    shuffle(chunks)
    sha256 = file_chunks_data["digest"]

    upload, _ = pulpcore_upload_chunks(size, chunks, sha256)

    with pytest.raises(ApiException) as e:
        pulpcore_bindings.UploadsApi.read(upload.pulp_href)

    assert e.value.status == 404


def test_upload_owner(pulpcore_bindings, gen_user, gen_object_with_cleanup):
    user = gen_user(model_roles=["core.upload_creator"])
    with user:
        upload = gen_object_with_cleanup(pulpcore_bindings.UploadsApi, {"size": 1024})
        pulpcore_bindings.UploadsApi.read(upload.pulp_href)
        assert set(pulpcore_bindings.UploadsApi.my_permissions(upload.pulp_href).permissions) == {
            "core.view_upload",
            "core.change_upload",
            "core.delete_upload",
            "core.manage_roles_upload",
        }
