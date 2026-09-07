"""
Regression test for https://github.com/pulp/pulpcore/issues/8041

``ArtifactFileField.pre_save`` used a raw ``startswith`` against ``settings.MEDIA_ROOT``
to detect files already in artifact storage. When ``MEDIA_ROOT`` is ``""``
(S3/Azure object-storage backends), ``os.path.join("", "artifact") == "artifact"``,
so any upload whose filename started with ``"artifact"`` was falsely detected as
already-stored and raised ``ValueError`` → HTTP 500.
"""

import os

import pytest


@pytest.mark.parametrize(
    "filename",
    [
        "artifact-foo-1.0-1.noarch.rpm",
        "artifact-bar.tar.gz",
    ],
)
def test_artifact_upload_artifact_prefix_filename_when_media_root_empty(
    pulpcore_bindings, tmp_path, pulp_settings, filename
):
    """Upload a file whose name starts with ``artifact`` — must succeed on object-storage backends.

    This test only applies when ``MEDIA_ROOT`` is empty (object-storage backends such
    as S3 and Azure). On filesystem backends the bug does not occur, so the test is
    skipped to avoid false positives.
    """
    if pulp_settings.MEDIA_ROOT:
        pytest.skip("Bug GH-8041 only affects backends where MEDIA_ROOT is empty (S3/Azure).")

    temp_file = tmp_path / filename
    temp_file.write_bytes(os.urandom(32))

    # Before the fix this raised HTTP 500 (ValueError in ArtifactFileField.pre_save).
    artifact = pulpcore_bindings.ArtifactsApi.create(str(temp_file))
    assert artifact.pulp_href is not None
