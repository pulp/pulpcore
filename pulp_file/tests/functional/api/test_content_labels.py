from uuid import uuid4

import os
import pytest
import uuid

from pulpcore.client.pulp_file.models import SetLabel, UnsetLabel
from pulpcore.client.pulp_file.exceptions import ForbiddenException, BadRequestException


@pytest.mark.parallel
def test_content_with_labels(
    pulpcore_bindings, file_repository_factory, gen_user, tmp_path, file_bindings, monitor_task
):
    """Test upload/-wth/search/set/unset content-labels."""

    def _create_labelled_content(repo, lbls, rel_path):
        temp_file = tmp_path / str(uuid.uuid4())
        temp_file.write_bytes(os.urandom(128))
        kwargs = {
            "file": str(temp_file),
            "repository": repo.pulp_href,
            "pulp_labels": lbls,
            "relative_path": rel_path,
        }
        # Upload content with a set of labels
        created = monitor_task(
            file_bindings.ContentFilesApi.create(**kwargs).task
        ).created_resources
        assert 2 == len(created)
        return file_bindings.ContentFilesApi.read(created[1]), created[0]

    # Create a repo to upload-into
    file_repo = file_repository_factory(name=str(uuid4()))
    labels = {"key_a": "value_a", "key_b": "value_b"}

    # Create a file to upload
    content, rv = _create_labelled_content(file_repo, labels, "1.iso")
    rtrn_labels = content.pulp_labels
    assert rtrn_labels == labels

    # Search for an exact label
    rslt = file_bindings.ContentFilesApi.list(
        pulp_label_select="key_b=value_b", repository_version=rv
    )
    assert 1 == rslt.count
    assert rslt.results[0].pulp_href == content.pulp_href

    # Search for an exact label whose value doesn't exist
    rslt = file_bindings.ContentFilesApi.list(
        pulp_label_select="key_b=value_XXX", repository_version=rv
    )
    assert 0 == rslt.count

    # Search for a key
    rslt = file_bindings.ContentFilesApi.list(pulp_label_select="key_a", repository_version=rv)
    assert 1 == rslt.count

    # Upload a second file with different values for the keys
    labels2 = {"key_a": "value_aa", "key_b1": "value_b1"}
    content2, rv2 = _create_labelled_content(file_repo, labels2, "2.iso")

    # Search for key_a, expect two results
    rslt = file_bindings.ContentFilesApi.list(pulp_label_select="key_a", repository_version=rv2)
    assert 2 == rslt.count
    # Search for key_b, expect one result
    rslt = file_bindings.ContentFilesApi.list(pulp_label_select="key_b", repository_version=rv2)
    assert 1 == rslt.count

    # Search using the "generic Content" list-api
    rslt = pulpcore_bindings.ContentApi.list(pulp_label_select="key_a", repository_version=rv2)
    assert 2 == rslt.count

    # Search using the "generic Content" list-api Q-filter
    q_filter = f'pulp_label_select="key_a" AND repository_version="{rv2}"'
    rslt = pulpcore_bindings.ContentApi.list(q=q_filter)
    assert 2 == rslt.count

    # Set a new label
    sl = SetLabel(key="nulabel", value="nuvalue")
    file_bindings.ContentFilesApi.set_label(content2.pulp_href, sl)
    content2 = file_bindings.ContentFilesApi.read(content2.pulp_href)
    nulabels = content2.pulp_labels
    assert "nulabel" in nulabels
    assert "key_a" in nulabels
    assert "key_b1" in nulabels

    # Change an existing label
    sl = SetLabel(key="nulabel", value="XXX")
    file_bindings.ContentFilesApi.set_label(content2.pulp_href, sl)
    content2 = file_bindings.ContentFilesApi.read(content2.pulp_href)
    nulabels = content2.pulp_labels
    assert nulabels["nulabel"] == "XXX"

    # Unset a label
    sl = UnsetLabel(key="key_a")
    file_bindings.ContentFilesApi.unset_label(content2.pulp_href, sl)
    content2 = file_bindings.ContentFilesApi.read(content2.pulp_href)
    assert "key_a" not in content2.pulp_labels
    # Search for key_a, expect two results
    rslt = file_bindings.ContentFilesApi.list(pulp_label_select="key_a", repository_version=rv2)
    assert 1 == rslt.count


@pytest.mark.parallel
def test_content_with_labels_permissions(
    file_repository_factory, gen_user, tmp_path, file_bindings, monitor_task
):
    def _create_labelled_content(repo, lbls, rel_path):
        temp_file = tmp_path / str(uuid.uuid4())
        temp_file.write_bytes(os.urandom(128))
        kwargs = {
            "file": str(temp_file),
            "repository": repo.pulp_href,
            "pulp_labels": lbls,
            "relative_path": rel_path,
        }
        # Upload content with a set of labels
        created = monitor_task(
            file_bindings.ContentFilesApi.create(**kwargs).task
        ).created_resources
        assert 2 == len(created)
        return file_bindings.ContentFilesApi.read(created[1]), created[0]

    # Create a repo to upload-into
    file_repo = file_repository_factory(name=str(uuid4()))
    labels = {"test_one": "ONE", "test_two": "TWO"}
    # Create a file to upload
    content, rv = _create_labelled_content(file_repo, labels, "1.iso")

    # Show that a "normal" user has no access to set/unset_label, even when they can access content
    norman = gen_user(model_roles=["file.filerepository_viewer"])
    with norman:
        with pytest.raises(ForbiddenException):
            sl = SetLabel(key="test_one", value="NOT-ONE")
            file_bindings.ContentFilesApi.set_label(content.pulp_href, sl)
        with pytest.raises(ForbiddenException):
            sl = UnsetLabel(key="test_two")
            file_bindings.ContentFilesApi.unset_label(content.pulp_href, sl)

    # Show that a repository-owner CANNOT upload content-with-labels
    repo_owner1 = gen_user(model_roles=["file.filerepository_creator"])
    with repo_owner1:
        file_repo = file_repository_factory(name=str(uuid4()))
        labels = {"test_one": "ONE", "test_two": "TWO"}
        # Create a file to upload
        with pytest.raises(BadRequestException):
            _, _ = _create_labelled_content(file_repo, labels, "2.iso")

    # Show that a repository-owner with content-labeler CAN upload content-with-labels
    repo_owner2 = gen_user(model_roles=["file.filerepository_creator", "core.content_labeler"])
    with repo_owner2:
        file_repo = file_repository_factory(name=str(uuid4()))
        labels = {"test_one": "ONE", "test_two": "TWO"}
        # Create a file to upload
        _, _ = _create_labelled_content(file_repo, labels, "2.iso")

    # Show that a user with the right role has access to set/unset_labels on any content they
    # can "see""
    just_labeler = gen_user(model_roles=["core.content_labeler", "file.filerepository_viewer"])
    with just_labeler:
        sl = SetLabel(key="new-test_one", value="NOT-NOT-ONE")
        file_bindings.ContentFilesApi.set_label(content.pulp_href, sl)
        sl = UnsetLabel(key="new-test_one")
        file_bindings.ContentFilesApi.unset_label(content.pulp_href, sl)
