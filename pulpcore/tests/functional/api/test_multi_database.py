import uuid

import pytest


@pytest.fixture
def satellite_domain(request, pulp_settings, pulpcore_bindings, gen_object_with_cleanup):
    if not pulp_settings.DOMAIN_ENABLED or "data_1" not in pulp_settings.DATABASES:
        pytest.skip("Requires a satellite database")
    return gen_object_with_cleanup(
        pulpcore_bindings.DomainsApi,
        {
            "name": str(uuid.uuid4()),
            "storage_class": "pulpcore.app.models.storage.FileSystem",
            "storage_settings": {"location": "/var/lib/pulp/media/"},
            "database_alias": getattr(request, "param", "data_1"),
        },
    )


def test_ordinary_relations_still_reject_another_domains_guard(
    satellite_domain,
    pulpcore_bindings,
    file_bindings,
    gen_object_with_cleanup,
):
    guard = gen_object_with_cleanup(
        pulpcore_bindings.ContentguardsHeaderApi,
        {"name": str(uuid.uuid4()), "header_name": "X-Test", "header_value": "secret"},
        pulp_domain=satellite_domain.name,
    )
    with pytest.raises(file_bindings.ApiException) as error:
        file_bindings.DistributionsFileApi.create(
            {
                "name": str(uuid.uuid4()),
                "base_path": str(uuid.uuid4()),
                "content_guard": guard.pulp_href,
            },
        )
    assert error.value.status == 400


@pytest.mark.parametrize("group_grant", [False, True])
def test_roles_and_grants_are_database_local(
    satellite_domain,
    pulpcore_bindings,
    file_bindings,
    gen_object_with_cleanup,
    gen_user,
    group_grant,
):
    name = str(uuid.uuid4())
    default_role = gen_object_with_cleanup(
        pulpcore_bindings.RolesApi,
        {"name": name, "permissions": ["file.view_filerepository"]},
    )
    assert pulpcore_bindings.RolesApi.list(name=name, pulp_domain=satellite_domain.name).count == 0
    satellite_role = gen_object_with_cleanup(
        pulpcore_bindings.RolesApi,
        {"name": name, "permissions": ["file.view_filerepository"]},
        pulp_domain=satellite_domain.name,
    )
    assert satellite_role.prn != default_role.prn
    assert f"/{satellite_domain.name}/" in satellite_role.pulp_href
    user = gen_user()
    if group_grant:
        group = gen_object_with_cleanup(pulpcore_bindings.GroupsApi, {"name": str(uuid.uuid4())})
        pulpcore_bindings.GroupsUsersApi.create(group.pulp_href, {"username": user.username})
        role_api = pulpcore_bindings.GroupsRolesApi
        entity_href = group.pulp_href
    else:
        role_api = pulpcore_bindings.UsersRolesApi
        entity_href = user.user.pulp_href
    grant = role_api.create(
        entity_href.replace("/default/", f"/{satellite_domain.name}/"),
        {"role": name, "domain": None, "content_object": None},
    )
    assert f"/{satellite_domain.name}/" in grant.pulp_href
    gen_object_with_cleanup(
        file_bindings.RepositoriesFileApi,
        {"name": str(uuid.uuid4())},
        pulp_domain=satellite_domain.name,
    )
    with user:
        assert file_bindings.RepositoriesFileApi.list(pulp_domain=satellite_domain.name).count == 1
        assert file_bindings.RepositoriesFileApi.list().count == 0
    pulpcore_bindings.RolesApi.partial_update(satellite_role.pulp_href, {"permissions": []})
    with user:
        assert file_bindings.RepositoriesFileApi.list(pulp_domain=satellite_domain.name).count == 0
    assert pulpcore_bindings.RolesApi.read(default_role.pulp_href).permissions == [
        "file.view_filerepository"
    ]


def test_domain_database_cannot_be_changed(satellite_domain, pulpcore_bindings):
    with pytest.raises(pulpcore_bindings.ApiException) as error:
        pulpcore_bindings.DomainsApi.partial_update(
            satellite_domain.pulp_href,
            {"database_alias": "default"},
        )
    assert error.value.status == 400


def test_domain_grant_uses_target_database_from_default_endpoint(
    satellite_domain,
    pulpcore_bindings,
    file_bindings,
    gen_object_with_cleanup,
    gen_user,
):
    role = gen_object_with_cleanup(
        pulpcore_bindings.RolesApi,
        {"name": str(uuid.uuid4()), "permissions": ["file.view_filerepository"]},
        pulp_domain=satellite_domain.name,
    )
    user = gen_user()
    grant = pulpcore_bindings.UsersRolesApi.create(
        user.user.pulp_href,
        {"role": role.name, "domain": satellite_domain.pulp_href, "content_object": None},
    )
    assert f"/{satellite_domain.name}/" in grant.pulp_href
    gen_object_with_cleanup(
        file_bindings.RepositoriesFileApi,
        {"name": str(uuid.uuid4())},
        pulp_domain=satellite_domain.name,
    )
    with user:
        assert file_bindings.RepositoriesFileApi.list(pulp_domain=satellite_domain.name).count == 1
        assert file_bindings.RepositoriesFileApi.list().count == 0
    pulpcore_bindings.UsersRolesApi.delete(grant.pulp_href)
    with user:
        assert file_bindings.RepositoriesFileApi.list(pulp_domain=satellite_domain.name).count == 0


@pytest.fixture
def satellite_task(satellite_domain, file_bindings, monitor_task, add_to_cleanup):
    name = str(uuid.uuid4())
    task = monitor_task(
        file_bindings.DistributionsFileApi.create(
            {"name": name, "base_path": name}, pulp_domain=satellite_domain.name
        ).task
    )
    add_to_cleanup(file_bindings.DistributionsFileApi, task.created_resources[0])
    return task


def test_object_grant_on_satellite_task(satellite_task, pulpcore_bindings, gen_user):
    user = gen_user()
    with user, pytest.raises(pulpcore_bindings.ApiException):
        pulpcore_bindings.TasksApi.read(satellite_task.pulp_href)
    pulpcore_bindings.UsersRolesApi.create(
        user.user.pulp_href,
        {"role": "core.task_owner", "content_object": satellite_task.pulp_href},
    )
    with user:
        assert pulpcore_bindings.TasksApi.read(satellite_task.pulp_href).pulp_href


def test_domain_grant_on_satellite_tasks(
    satellite_domain, satellite_task, pulpcore_bindings, gen_user
):
    user = gen_user(domain_roles=[("core.task_viewer", satellite_domain.pulp_href)])
    with user:
        hrefs = [
            task.pulp_href
            for task in pulpcore_bindings.TasksApi.list(pulp_domain=satellite_domain.name).results
        ]
        assert satellite_task.pulp_href in hrefs
        assert pulpcore_bindings.TasksApi.read(satellite_task.pulp_href).pulp_href
