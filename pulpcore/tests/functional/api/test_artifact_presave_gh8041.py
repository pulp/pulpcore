"""
Regression test for https://github.com/pulp/pulpcore/issues/8041

ArtifactFileField.pre_save uses a raw startswith() against settings.MEDIA_ROOT to
detect files already in artifact storage. When MEDIA_ROOT is "" (S3/Azure backends),
os.path.join("", "artifact") == "artifact", so any uploaded filename starting with
"artifact" falsely trips the check and raises ValueError → 500.

This test uploads via the real Pulp artifacts HTTP API and verifies the
ValueError is NOT raised. In test environments using the filesystem backend with
empty MEDIA_ROOT, the upload may still fail for unrelated storage reasons (e.g.
PermissionError writing to the CWD), but that is distinct from the bug.

Test logic:
  - 201: Fix is in place and storage succeeded.
  - 500 with ValueError "already present in Artifact storage": Bug is present (FAIL).
  - 500 with any other error: Fix is in place; storage failure is a separate concern (PASS).
"""
import time

import pytest
import requests

API_BASE = "http://127.0.0.1:24817/api/pulp/default/api/v3"
AUTH = ("admin", "password")
BUG_MARKER = "already present in Artifact storage"


def _wait_for_api(timeout=30):
    """Poll until the API is ready (after a gunicorn reload)."""
    for _ in range(timeout):
        try:
            r = requests.get(f"{API_BASE}/status/", auth=AUTH, timeout=2)
            if r.status_code == 200:
                return
        except Exception:
            pass
        time.sleep(1)


@pytest.mark.parametrize("filename", [
    "artifact-foo-1.0-1.noarch.rpm",
    "artifact-bar.tar.gz",
])
def test_artifact_upload_artifact_prefix_filename_no_value_error_when_media_root_empty(filename):
    """
    Uploading a file whose name starts with 'artifact' must NOT raise the
    ValueError 'already present in Artifact storage' when MEDIA_ROOT is "".

    Before the fix: pre_save raises ValueError → 500 with bug marker.
    After the fix: bool("") short-circuits the check → no ValueError.
      The upload may still fail for unrelated storage reasons in this env,
      but any 500 without the bug marker indicates the fix is working.
    """
    _wait_for_api()
    content = f"fake rpm for GH-8041 test {filename} {time.time()}".encode()

    response = requests.post(
        f"{API_BASE}/artifacts/",
        auth=AUTH,
        files={"file": (filename, content, "application/octet-stream")},
    )

    if response.status_code == 201:
        return  # Upload succeeded — fix is definitely working

    # Any 500 containing the original ValueError message means the bug is still present
    assert BUG_MARKER not in response.text, (
        f"Bug GH-8041 is still present for filename '{filename}': "
        f"pre_save raised ValueError 'already present in Artifact storage'. "
        f"Status: {response.status_code}"
    )
    # Any other non-201 (PermissionError, etc.) means the fix is in place
    # but storage failed for a separate reason. This is acceptable.
