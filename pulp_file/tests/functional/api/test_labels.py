from uuid import uuid4

import pytest

from pulpcore.client.pulp_file.exceptions import ApiException


@pytest.mark.parallel
def test_create_repo_with_labels(file_repository_factory):
    """Create repository with labels."""

    labels = {"key_a": "label_a"}
    file_repo = file_repository_factory(name=str(uuid4()), pulp_labels=labels)
    assert labels == file_repo.pulp_labels


@pytest.mark.parallel
def test_set_unset_all_labels(file_repo, file_bindings, monitor_task):
    """Set and unset labels from a repository."""

    assert file_repo.pulp_labels == {}

    # Set some labels
    labels = {"key_a": "label_a"}
    monitor_task(
        file_bindings.RepositoriesFileApi.partial_update(
            file_repo.pulp_href, {"pulp_labels": labels}
        ).task
    )
    file_repo = file_bindings.RepositoriesFileApi.read(file_repo.pulp_href)
    assert file_repo.pulp_labels == labels

    # Unset all labels
    monitor_task(
        file_bindings.RepositoriesFileApi.partial_update(
            file_repo.pulp_href, {"pulp_labels": {}}
        ).task
    )
    file_repo = file_bindings.RepositoriesFileApi.read(file_repo.pulp_href)
    assert file_repo.pulp_labels == {}


@pytest.mark.parallel
def test_add_remove_label_keys(file_repo, file_bindings, file_repository_factory, monitor_task):
    """Add and Remove labels by key."""

    # Set some initial labels
    labels = {"key_a": "label_a"}
    file_repo = file_repository_factory(name=str(uuid4()), pulp_labels=labels)

    # Add a new key
    labels["key_b"] = "label_b"
    monitor_task(
        file_bindings.RepositoriesFileApi.partial_update(
            file_repo.pulp_href, {"pulp_labels": labels}
        ).task
    )

    file_repo = file_bindings.RepositoriesFileApi.read(file_repo.pulp_href)
    assert file_repo.pulp_labels == labels

    # Remove the original key
    del labels["key_a"]
    monitor_task(
        file_bindings.RepositoriesFileApi.partial_update(
            file_repo.pulp_href, {"pulp_labels": labels}
        ).task
    )

    file_repo = file_bindings.RepositoriesFileApi.read(file_repo.pulp_href)
    assert file_repo.pulp_labels == labels


@pytest.mark.parallel
def test_update_existing_label_value(file_bindings, file_repository_factory, monitor_task):
    """Update an existing label."""

    # Set some initial labels
    labels = {"key_a": "label_a"}
    file_repo = file_repository_factory(name=str(uuid4()), pulp_labels=labels)

    # Modify the value of an existing key
    labels["key_a"] = "label_b"
    monitor_task(
        file_bindings.RepositoriesFileApi.partial_update(
            file_repo.pulp_href, {"pulp_labels": labels}
        ).task
    )

    file_repo = file_bindings.RepositoriesFileApi.read(file_repo.pulp_href)
    assert file_repo.pulp_labels == labels


@pytest.mark.parallel
def test_model_partial_update(file_repository_factory, file_bindings, monitor_task):
    """Test that labels aren't unset accidentally with PATCH calls of other fields."""

    # Set some initial labels
    labels = {"key_a": "label_a"}
    file_repo = file_repository_factory(name=str(uuid4()), pulp_labels=labels)

    # Update the name only
    monitor_task(
        file_bindings.RepositoriesFileApi.partial_update(
            file_repo.pulp_href, {"name": str(uuid4())}
        ).task
    )

    file_repo = file_bindings.RepositoriesFileApi.read(file_repo.pulp_href)
    assert file_repo.pulp_labels == labels


@pytest.mark.parallel
def test_invalid_label_type(file_repository_factory):
    """Test that label doesn't accept non-dicts"""

    with pytest.raises(ApiException) as e_info:
        labels = "key_a"  # str instead of dict
        file_repository_factory(name=str(uuid4()), pulp_labels=labels)
    assert e_info.value.status == 400


@pytest.mark.parallel
def test_invalid_labels(file_repository_factory):
    """Test that label keys and values are validated."""
    with pytest.raises(ApiException) as e_info:
        file_repository_factory(name=str(uuid4()), pulp_labels={"@": "maia"})
    assert e_info.value.status == 400

    with pytest.raises(ApiException) as e_info:
        file_repository_factory(name=str(uuid4()), pulp_labels={"arda": "eru,illuvata"})
    assert e_info.value.status == 400


# Label Filtering


@pytest.mark.parallel
def test_label_select(file_repository_factory, file_bindings):
    """Test lots of select types."""
    key1 = str(uuid4()).replace("-", "")  # We can only have alphanumerics
    key2 = str(uuid4()).replace("-", "")  # We can only have alphanumerics

    labels = {key1: "production", key2: "true"}
    file_repository_factory(name=str(uuid4()), pulp_labels=labels)

    labels = {key1: "staging", key2: "false"}
    file_repository_factory(name=str(uuid4()), pulp_labels=labels)

    file_repository_factory(name=str(uuid4()), pulp_labels={})

    results = file_bindings.RepositoriesFileApi.list(pulp_label_select=f"{key1}=production").results
    assert len(results) == 1

    results = file_bindings.RepositoriesFileApi.list(
        pulp_label_select=f"{key1}!=production"
    ).results
    assert len(results) == 1

    results = file_bindings.RepositoriesFileApi.list(pulp_label_select=key1).results
    assert len(results) == 2

    results = file_bindings.RepositoriesFileApi.list(pulp_label_select=f"{key1}~prod").results
    assert len(results) == 1

    results = file_bindings.RepositoriesFileApi.list(
        pulp_label_select=f"{key1}=production,{key2}=true"
    ).results
    assert len(results) == 1

    results = file_bindings.RepositoriesFileApi.list(
        pulp_label_select=f"{key1}=production,{key2}!=false"
    ).results
    assert len(results) == 1

    results = file_bindings.RepositoriesFileApi.list(
        pulp_label_select=f"!{key1},{key2}=false"
    ).results
    assert len(results) == 0


@pytest.mark.parallel
def test_empty_blank_filter(file_repository_factory, file_bindings):
    """Test filtering values with a blank string."""
    key = str(uuid4()).replace("-", "")  # We can only have alphanumerics

    labels = {key: ""}
    file_repository_factory(name=str(uuid4()), pulp_labels=labels)

    results = file_bindings.RepositoriesFileApi.list(pulp_label_select=f"{key}=").results
    assert len(results) == 1

    results = file_bindings.RepositoriesFileApi.list(pulp_label_select=f"{key}~").results
    assert len(results) == 1


@pytest.mark.parallel
def test_invalid_label_select(file_bindings):
    """Test removing all labels."""

    with pytest.raises(ApiException) as e_info:
        file_bindings.RepositoriesFileApi.list(pulp_label_select="").results
    assert e_info.value.status == 400

    with pytest.raises(ApiException) as e_info:
        file_bindings.RepositoriesFileApi.list(pulp_label_select="!environment=production").results
    assert e_info.value.status == 400

    with pytest.raises(ApiException) as e_info:
        file_bindings.RepositoriesFileApi.list(pulp_label_select="=bad filter").results
    assert e_info.value.status == 400
