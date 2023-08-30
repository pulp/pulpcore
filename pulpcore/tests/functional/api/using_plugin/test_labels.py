import pytest


@pytest.fixture
def label_access_policy(access_policies_api_client):
    orig_access_policy = access_policies_api_client.list(
        viewset_name="repositories/file/file"
    ).results[0]
    new_statements = orig_access_policy.statements.copy()
    new_statements.append(
        {
            "action": ["set_label", "unset_label"],
            "effect": "allow",
            "condition": [
                "has_model_or_domain_or_obj_perms:file.modify_filerepository",
                "has_model_or_domain_or_obj_perms:file.view_filerepository",
            ],
            "principal": "authenticated",
        }
    )
    access_policies_api_client.partial_update(
        orig_access_policy.pulp_href, {"statements": new_statements}
    )
    yield
    if orig_access_policy.customized:
        access_policies_api_client.partial_update(
            orig_access_policy.pulp_href, {"statements": orig_access_policy.statements}
        )
    else:
        access_policies_api_client.reset(orig_access_policy.pulp_href)


@pytest.mark.parallel
def test_set_label(label_access_policy, file_repository_api_client, file_repository_factory):
    repository = file_repository_factory()
    assert repository.pulp_labels == {}

    file_repository_api_client.set_label(repository.pulp_href, {"key": "a", "value": None})
    file_repository_api_client.set_label(repository.pulp_href, {"key": "b", "value": ""})
    file_repository_api_client.set_label(repository.pulp_href, {"key": "c", "value": "val1"})
    file_repository_api_client.set_label(repository.pulp_href, {"key": "d", "value": "val2"})
    file_repository_api_client.set_label(repository.pulp_href, {"key": "e", "value": "val3"})
    file_repository_api_client.set_label(repository.pulp_href, {"key": "c", "value": "val4"})
    file_repository_api_client.set_label(repository.pulp_href, {"key": "d", "value": None})

    repository = file_repository_api_client.read(repository.pulp_href)
    assert repository.pulp_labels == {
        "a": None,
        "b": "",
        "c": "val4",
        "d": None,
        "e": "val3",
    }

    file_repository_api_client.unset_label(repository.pulp_href, {"key": "e"})

    repository = file_repository_api_client.read(repository.pulp_href)
    assert repository.pulp_labels == {
        "a": None,
        "b": "",
        "c": "val4",
        "d": None,
    }
