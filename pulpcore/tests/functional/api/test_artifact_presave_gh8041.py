"""
Regression test for https://github.com/pulp/pulpcore/issues/8041

ArtifactFileField.pre_save uses a raw startswith() against settings.MEDIA_ROOT to
detect files already in artifact storage. When MEDIA_ROOT is "" (S3/Azure backends),
os.path.join("", "artifact") == "artifact", so any uploaded filename starting with
"artifact" falsely trips the check and raises ValueError → 500.
"""
import os
import time
import tempfile

import pytest

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "pulpcore.app.settings")
os.environ.setdefault("PULP_SETTINGS", "/etc/pulp/settings.py")


@pytest.mark.django_db
def test_artifact_upload_artifact_prefix_filename_no_value_error_when_media_root_empty():
    """
    Uploading a file whose name starts with 'artifact' must not raise ValueError
    when MEDIA_ROOT is empty (S3/object-storage backend condition).

    Before the fix: pre_save raises ValueError because
      os.path.join("", "artifact") == "artifact"
      and file.name.startswith("artifact") is True.
    After the fix: bool("") is False so the guard short-circuits and no
      ValueError is raised.
    """
    from django.test import override_settings
    from django.core.files.uploadedfile import SimpleUploadedFile
    from django.contrib.auth.models import User
    from rest_framework.test import APIClient

    client = APIClient()
    user = User.objects.create_superuser("testadmin_gh8041", "test@example.com", "password")
    client.force_authenticate(user=user)

    filename = "artifact-foo-1.0-1.noarch.rpm"
    # Unique content per run to avoid SHA256 uniqueness conflicts
    content = f"fake rpm for GH-8041 test {time.time()}".encode()

    with tempfile.TemporaryDirectory() as tmpdir:
        with override_settings(MEDIA_ROOT=""):
            f = SimpleUploadedFile(filename, content, content_type="application/octet-stream")
            response = client.post(
                "/api/pulp/default/api/v3/artifacts/",
                {"file": f},
                format="multipart",
            )

    assert response.status_code == 201, (
        f"Expected HTTP 201 but got {response.status_code}. "
        f"Response: {getattr(response, 'data', response.content[:300])}"
    )
