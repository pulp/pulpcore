"""Tests related to the AccessPolicy."""

import pytest


@pytest.mark.parallel
def test_access_policy_cannot_be_created(pulpcore_bindings):
    """Test that only plugin writers can ship a new AccessPolicy."""
    assert not hasattr(pulpcore_bindings.AccessPoliciesApi, "create")


@pytest.mark.parallel
def test_access_policy_default_policies(pulpcore_bindings):
    """Test that the default policies from pulpcore are installed."""
    groups_response = pulpcore_bindings.AccessPoliciesApi.list(viewset_name="groups")
    assert groups_response.count == 1

    groups_users_response = pulpcore_bindings.AccessPoliciesApi.list(viewset_name="groups/users")
    assert groups_users_response.count == 1

    tasks_response = pulpcore_bindings.AccessPoliciesApi.list(viewset_name="tasks")
    assert tasks_response.count == 1


def test_statements_attr_can_be_modified(pulpcore_bindings):
    """Test that `AccessPolicy.statements` can be modified"""
    tasks_response = pulpcore_bindings.AccessPoliciesApi.list(viewset_name="tasks")
    tasks_href = tasks_response.results[0].pulp_href
    task_access_policy = pulpcore_bindings.AccessPoliciesApi.read(tasks_href)

    original_statements = task_access_policy.statements
    assert not task_access_policy.customized
    assert original_statements != []

    pulpcore_bindings.AccessPoliciesApi.partial_update(tasks_href, {"statements": []})
    task_access_policy = pulpcore_bindings.AccessPoliciesApi.read(tasks_href)
    assert task_access_policy.customized
    assert task_access_policy.statements == []

    pulpcore_bindings.AccessPoliciesApi.reset(tasks_href)
    task_access_policy = pulpcore_bindings.AccessPoliciesApi.read(tasks_href)
    assert not task_access_policy.customized
    assert task_access_policy.statements == original_statements


def test_creation_hooks_attr_can_be_modified(pulpcore_bindings):
    """Test that `AccessPolicy.creation_hooks` can be modified"""
    groups_response = pulpcore_bindings.AccessPoliciesApi.list(viewset_name="groups")
    groups_href = groups_response.results[0].pulp_href
    groups_access_policy = pulpcore_bindings.AccessPoliciesApi.read(groups_href)

    original_creation_hooks = groups_access_policy.creation_hooks
    assert not groups_access_policy.customized
    assert original_creation_hooks != []

    pulpcore_bindings.AccessPoliciesApi.partial_update(groups_href, {"creation_hooks": []})
    groups_access_policy = pulpcore_bindings.AccessPoliciesApi.read(groups_href)
    assert groups_access_policy.customized
    assert groups_access_policy.creation_hooks == []

    pulpcore_bindings.AccessPoliciesApi.reset(groups_href)
    groups_access_policy = pulpcore_bindings.AccessPoliciesApi.read(groups_href)
    assert not groups_access_policy.customized
    assert groups_access_policy.creation_hooks == original_creation_hooks


@pytest.mark.parallel
def test_customized_is_read_only(pulpcore_bindings):
    """Test that the `AccessPolicy.customized` attribute is read only"""
    tasks_response = pulpcore_bindings.AccessPoliciesApi.list(viewset_name="tasks")
    tasks_href = tasks_response.results[0].pulp_href
    task_access_policy = pulpcore_bindings.AccessPoliciesApi.read(tasks_href)

    response = pulpcore_bindings.AccessPoliciesApi.partial_update(
        tasks_href, {"customized": not task_access_policy.customized}
    )
    assert response.customized == task_access_policy.customized


@pytest.mark.parallel
def test_viewset_name_is_read_only(pulpcore_bindings):
    """Test that the `AccessPolicy.viewset_name` attribute is read only"""
    tasks_response = pulpcore_bindings.AccessPoliciesApi.list(viewset_name="tasks")
    tasks_href = tasks_response.results[0].pulp_href
    task_access_policy = pulpcore_bindings.AccessPoliciesApi.read(tasks_href)

    response = pulpcore_bindings.AccessPoliciesApi.partial_update(
        tasks_href, {"viewset_name": "not-a-real-name"}
    )
    assert response.viewset_name == task_access_policy.viewset_name
