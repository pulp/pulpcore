"""
Regression test for https://github.com/pulp/pulpcore/issues/8041

ArtifactFileField.pre_save uses a raw startswith() against settings.MEDIA_ROOT to
detect files already in artifact storage. When MEDIA_ROOT is "" (S3/Azure backends),
os.path.join("", "artifact") == "artifact", so any uploaded filename starting with
"artifact" falsely trips the check and raises ValueError → 500.

This test uploads a file named "artifact-foo-1.0-1.noarch.rpm" via the real Pulp
artifacts HTTP API and asserts HTTP 201.
Run against a container started with MEDIA_ROOT="" (PULP_MEDIA_ROOT=).
"""
import sys
import time

import pytest
import requests

# API accessible from inside the container
API_BASE = "http://127.0.0.1:24817/api/pulp/default/api/v3"
AUTH = ("admin", "password")


@pytest.mark.parametrize("filename", [
    "artifact-foo-1.0-1.noarch.rpm",
    "artifact-bar.tar.gz",
])
def test_artifact_upload_artifact_prefix_filename_no_500_when_media_root_empty(filename):
    """
    Uploading a file whose name starts with 'artifact' must return 201
    when MEDIA_ROOT is empty (S3/object-storage backend condition).

    Before the fix: pre_save raises ValueError → HTTP 500.
    After the fix: the guard bool(settings.MEDIA_ROOT) short-circuits
      and the upload succeeds.
    """
    content = f"fake rpm for GH-8041 test {filename} {time.time()}".encode()

    response = requests.post(
        f"{API_BASE}/artifacts/",
        auth=AUTH,
        files={"file": (filename, content, "application/octet-stream")},
    )

    assert response.status_code == 201, (
        f"Expected HTTP 201 for filename '{filename}' but got {response.status_code}. "
        f"Body: {response.text[:500]}"
    )
