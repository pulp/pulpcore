"""Tests that CRUD file remotes."""

import json
import uuid

import pytest

from pulpcore.client.pulp_file.exceptions import ApiException


@pytest.mark.parallel
def test_remote_crud_workflow(file_bindings, gen_object_with_cleanup, monitor_task):
    remote_data = {"name": str(uuid.uuid4()), "url": "http://example.com"}
    remote = gen_object_with_cleanup(file_bindings.RemotesFileApi, remote_data)
    assert remote.url == remote_data["url"]
    assert remote.name == remote_data["name"]

    with pytest.raises(ApiException) as exc:
        gen_object_with_cleanup(file_bindings.RemotesFileApi, remote_data)
    assert exc.value.status == 400
    assert json.loads(exc.value.body) == {"name": ["This field must be unique."]}

    update_response = file_bindings.RemotesFileApi.partial_update(
        remote.pulp_href, {"url": "https://example.com"}
    )
    task = monitor_task(update_response.task)
    assert task.created_resources == []

    remote = file_bindings.RemotesFileApi.read(remote.pulp_href)
    assert remote.url == "https://example.com"

    all_new_remote_data = {"name": str(uuid.uuid4()), "url": "http://example.com"}
    update_response = file_bindings.RemotesFileApi.update(remote.pulp_href, all_new_remote_data)
    task = monitor_task(update_response.task)
    assert task.created_resources == []

    remote = file_bindings.RemotesFileApi.read(remote.pulp_href)
    assert remote.name == all_new_remote_data["name"]
    assert remote.url == all_new_remote_data["url"]


@pytest.mark.parallel
def test_create_file_remote_with_invalid_parameter(file_bindings, gen_object_with_cleanup):
    unexpected_field_remote_data = {
        "name": str(uuid.uuid4()),
        "url": "http://example.com",
        "foo": "bar",
    }

    with pytest.raises(ApiException) as exc:
        gen_object_with_cleanup(file_bindings.RemotesFileApi, unexpected_field_remote_data)
    assert exc.value.status == 400
    assert json.loads(exc.value.body) == {"foo": ["Unexpected field"]}


@pytest.mark.parallel
def test_create_file_remote_without_url(file_bindings, gen_object_with_cleanup):
    with pytest.raises(ApiException) as exc:
        gen_object_with_cleanup(file_bindings.RemotesFileApi, {"name": str(uuid.uuid4())})
    assert exc.value.status == 400
    assert json.loads(exc.value.body) == {"url": ["This field is required."]}


@pytest.mark.parallel
def test_default_remote_policy_immediate(file_bindings, gen_object_with_cleanup):
    remote_data = {"name": str(uuid.uuid4()), "url": "http://example.com"}
    remote = gen_object_with_cleanup(file_bindings.RemotesFileApi, remote_data)
    assert remote.policy == "immediate"


@pytest.mark.parallel
def test_specify_remote_policy_streamed(file_bindings, gen_object_with_cleanup):
    remote_data = {"name": str(uuid.uuid4()), "url": "http://example.com", "policy": "streamed"}
    remote = gen_object_with_cleanup(file_bindings.RemotesFileApi, remote_data)
    assert remote.policy == "streamed"


@pytest.mark.parallel
def test_specify_remote_policy_on_demand(file_bindings, gen_object_with_cleanup):
    remote_data = {"name": str(uuid.uuid4()), "url": "http://example.com", "policy": "on_demand"}
    remote = gen_object_with_cleanup(file_bindings.RemotesFileApi, remote_data)
    assert remote.policy == "on_demand"


@pytest.mark.parallel
def test_can_update_remote_policy(file_bindings, gen_object_with_cleanup, monitor_task):
    initial_remote_data = {"name": str(uuid.uuid4()), "url": "http://example.com"}
    remote = gen_object_with_cleanup(file_bindings.RemotesFileApi, initial_remote_data)
    assert remote.policy == "immediate"

    update_response = file_bindings.RemotesFileApi.partial_update(
        remote.pulp_href, {"policy": "on_demand"}
    )
    monitor_task(update_response.task)

    remote = file_bindings.RemotesFileApi.read(remote.pulp_href)
    assert remote.policy == "on_demand"
