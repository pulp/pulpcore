import pytest


@pytest.fixture
def label_access_policy(pulpcore_bindings):
    orig_access_policy = pulpcore_bindings.AccessPoliciesApi.list(
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
    pulpcore_bindings.AccessPoliciesApi.partial_update(
        orig_access_policy.pulp_href, {"statements": new_statements}
    )
    yield
    if orig_access_policy.customized:
        pulpcore_bindings.AccessPoliciesApi.partial_update(
            orig_access_policy.pulp_href, {"statements": orig_access_policy.statements}
        )
    else:
        pulpcore_bindings.AccessPoliciesApi.reset(orig_access_policy.pulp_href)


@pytest.mark.parallel
def test_set_label(label_access_policy, file_bindings, file_repository_factory):
    repository = file_repository_factory()
    assert repository.pulp_labels == {}

    file_bindings.RepositoriesFileApi.set_label(repository.pulp_href, {"key": "a", "value": None})
    file_bindings.RepositoriesFileApi.set_label(repository.pulp_href, {"key": "b", "value": ""})
    file_bindings.RepositoriesFileApi.set_label(repository.pulp_href, {"key": "c", "value": "val1"})
    file_bindings.RepositoriesFileApi.set_label(repository.pulp_href, {"key": "d", "value": "val2"})
    file_bindings.RepositoriesFileApi.set_label(repository.pulp_href, {"key": "e", "value": "val3"})
    file_bindings.RepositoriesFileApi.set_label(repository.pulp_href, {"key": "c", "value": "val4"})
    file_bindings.RepositoriesFileApi.set_label(repository.pulp_href, {"key": "d", "value": None})

    repository = file_bindings.RepositoriesFileApi.read(repository.pulp_href)
    assert repository.pulp_labels == {
        "a": None,
        "b": "",
        "c": "val4",
        "d": None,
        "e": "val3",
    }

    file_bindings.RepositoriesFileApi.unset_label(repository.pulp_href, {"key": "e"})

    repository = file_bindings.RepositoriesFileApi.read(repository.pulp_href)
    assert repository.pulp_labels == {
        "a": None,
        "b": "",
        "c": "val4",
        "d": None,
    }
