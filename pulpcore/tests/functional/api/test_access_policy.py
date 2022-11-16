"""Tests related to the AccessPolicy."""

import pytest


@pytest.mark.parallel
def test_access_policy_cannot_be_created(access_policies_api_client):
    """Test that only plugin writers can ship a new AccessPolicy."""
    assert not hasattr(access_policies_api_client, "create")


@pytest.mark.parallel
def test_access_policy_default_policies(access_policies_api_client):
    """Test that the default policies from pulpcore are installed."""
    groups_response = access_policies_api_client.list(viewset_name="groups")
    assert groups_response.count == 1

    groups_users_response = access_policies_api_client.list(viewset_name="groups/users")
    assert groups_users_response.count == 1

    tasks_response = access_policies_api_client.list(viewset_name="tasks")
    assert tasks_response.count == 1


def test_statements_attr_can_be_modified(access_policies_api_client):
    """Test that `AccessPolicy.statements` can be modified"""
    tasks_response = access_policies_api_client.list(viewset_name="tasks")
    tasks_href = tasks_response.results[0].pulp_href
    task_access_policy = access_policies_api_client.read(tasks_href)

    original_statements = task_access_policy.statements
    assert not task_access_policy.customized
    assert original_statements != []

    access_policies_api_client.partial_update(tasks_href, {"statements": []})
    task_access_policy = access_policies_api_client.read(tasks_href)
    assert task_access_policy.customized
    assert task_access_policy.statements == []

    access_policies_api_client.reset(tasks_href)
    task_access_policy = access_policies_api_client.read(tasks_href)
    assert not task_access_policy.customized
    assert task_access_policy.statements == original_statements


def test_creation_hooks_attr_can_be_modified(access_policies_api_client):
    """Test that `AccessPolicy.creation_hooks` can be modified"""
    groups_response = access_policies_api_client.list(viewset_name="groups")
    groups_href = groups_response.results[0].pulp_href
    groups_access_policy = access_policies_api_client.read(groups_href)

    original_creation_hooks = groups_access_policy.creation_hooks
    assert not groups_access_policy.customized
    assert original_creation_hooks != []

    access_policies_api_client.partial_update(groups_href, {"creation_hooks": []})
    groups_access_policy = access_policies_api_client.read(groups_href)
    assert groups_access_policy.customized
    assert groups_access_policy.creation_hooks == []

    access_policies_api_client.reset(groups_href)
    groups_access_policy = access_policies_api_client.read(groups_href)
    assert not groups_access_policy.customized
    assert groups_access_policy.creation_hooks == original_creation_hooks


@pytest.mark.parallel
def test_customized_is_read_only(access_policies_api_client):
    """Test that the `AccessPolicy.customized` attribute is read only"""
    tasks_response = access_policies_api_client.list(viewset_name="tasks")
    tasks_href = tasks_response.results[0].pulp_href
    task_access_policy = access_policies_api_client.read(tasks_href)

    response = access_policies_api_client.partial_update(
        tasks_href, {"customized": not task_access_policy.customized}
    )
    assert response.customized == task_access_policy.customized


@pytest.mark.parallel
def test_viewset_name_is_read_only(access_policies_api_client):
    """Test that the `AccessPolicy.viewset_name` attribute is read only"""
    tasks_response = access_policies_api_client.list(viewset_name="tasks")
    tasks_href = tasks_response.results[0].pulp_href
    task_access_policy = access_policies_api_client.read(tasks_href)

    response = access_policies_api_client.partial_update(
        tasks_href, {"viewset_name": "not-a-real-name"}
    )
    assert response.viewset_name == task_access_policy.viewset_name
