"""Test content creator ownership (RBAC)."""

import uuid

import pytest


@pytest.mark.parallel
def test_content_creator_owner(
    file_bindings,
    gen_user,
    tmp_path,
):
    """Test that content creators can read their orphan content via object-owner grant.

    This test verifies that:
    1. A non-admin user can upload orphan FileContent (not in any repository)
    2. The creator can read the content back via object-owner grant
    3. The creator sees the content in their list
    4. A different non-admin user cannot see the content (neither read nor list)

    The key point is that read access works via the OBJECT-OWNER grant, not via
    repository scoping or model-level content-view permission.
    """
    # Create non-admin users with file.file_uploader role (grants file.upload_files)
    uploader = gen_user(model_roles=["file.file_uploader"])
    other = gen_user(model_roles=["file.file_uploader"])
    dedup_uploader = gen_user(model_roles=["file.file_uploader"])

    # Create a temporary file to upload
    file_path = tmp_path / "test_content.bin"
    file_path.write_bytes(b"test content for ownership")

    # Uploader uploads orphan content (no repository) via the upload action
    relative_path = str(uuid.uuid4())
    with uploader:
        content = file_bindings.ContentFilesApi.upload(
            file=str(file_path),
            relative_path=relative_path
        )
        href = content.pulp_href

    # Uploader can read their own content by href
    with uploader:
        retrieved = file_bindings.ContentFilesApi.read(href)
        assert retrieved.pulp_href == href
        assert retrieved.relative_path == relative_path

        # Content appears in uploader's list
        list_response = file_bindings.ContentFilesApi.list()
        assert any(c.pulp_href == href for c in list_response.results)

    # Other user cannot read the content (404, not 403, because it's filtered from their view)
    with other:
        with pytest.raises(file_bindings.module.ApiException) as exc:
            file_bindings.ContentFilesApi.read(href)
        assert exc.value.status == 404

        # Content does not appear in other's list
        list_response = file_bindings.ContentFilesApi.list()
        assert not any(c.pulp_href == href for c in list_response.results)

    # A user who uploads the SAME bytes deduplicates to the existing unit and gets
    # view-only access (they can read it back), but NOT the owner role.
    with dedup_uploader:
        deduped = file_bindings.ContentFilesApi.upload(
            file=str(file_path),
            relative_path=relative_path,
        )
        assert deduped.pulp_href == href

        retrieved = file_bindings.ContentFilesApi.read(href)
        assert retrieved.pulp_href == href
