import pytest
import uuid

from pulpcore.client.pulp_file import ApiException
from pulpcore.client.pulp_file import AsyncOperationResponse


@pytest.fixture()
def gen_users(gen_user):
    """Returns a user generator function for the tests."""

    def _gen_users(role_names=list()):
        if isinstance(role_names, str):
            role_names = [role_names]
        viewer_roles = [f"file.{role}_viewer" for role in role_names]
        creator_roles = [f"file.{role}_creator" for role in role_names]
        alice = gen_user(model_roles=viewer_roles)
        bob = gen_user(model_roles=creator_roles)
        charlie = gen_user()
        return alice, bob, charlie

    return _gen_users


@pytest.fixture
def try_action(monitor_task):
    def _try_action(user, client, action, outcome, *args, **kwargs):
        action_api = getattr(client, f"{action}_with_http_info")
        try:
            with user:
                response, status, _ = action_api(*args, **kwargs, _return_http_data_only=False)
            if isinstance(response, AsyncOperationResponse):
                response = monitor_task(response.task)
        except ApiException as e:
            assert e.status == outcome, f"{e}"
        else:
            assert status == outcome, f"User performed {action} when they shouldn't been able to"
            return response

    return _try_action


def test_basic_actions(gen_users, file_bindings, try_action, file_repo):
    """Test list, read, create, update and delete apis."""
    alice, bob, charlie = gen_users("filerepository")

    a_list = try_action(alice, file_bindings.RepositoriesFileApi, "list", 200)
    assert a_list.count >= 1
    b_list = try_action(bob, file_bindings.RepositoriesFileApi, "list", 200)
    c_list = try_action(charlie, file_bindings.RepositoriesFileApi, "list", 200)
    assert (b_list.count, c_list.count) == (0, 0)

    # Create testing
    try_action(alice, file_bindings.RepositoriesFileApi, "create", 403, {"name": str(uuid.uuid4())})
    repo = try_action(
        bob, file_bindings.RepositoriesFileApi, "create", 201, {"name": str(uuid.uuid4())}
    )
    try_action(
        charlie, file_bindings.RepositoriesFileApi, "create", 403, {"name": str(uuid.uuid4())}
    )

    # View testing
    try_action(alice, file_bindings.RepositoriesFileApi, "read", 200, repo.pulp_href)
    try_action(bob, file_bindings.RepositoriesFileApi, "read", 200, repo.pulp_href)
    try_action(charlie, file_bindings.RepositoriesFileApi, "read", 404, repo.pulp_href)

    # Update testing
    update_args = [repo.pulp_href, {"name": str(uuid.uuid4())}]
    try_action(alice, file_bindings.RepositoriesFileApi, "partial_update", 403, *update_args)
    try_action(bob, file_bindings.RepositoriesFileApi, "partial_update", 202, *update_args)
    try_action(charlie, file_bindings.RepositoriesFileApi, "partial_update", 404, *update_args)

    # Delete testing
    try_action(alice, file_bindings.RepositoriesFileApi, "delete", 403, repo.pulp_href)
    try_action(charlie, file_bindings.RepositoriesFileApi, "delete", 404, repo.pulp_href)
    try_action(bob, file_bindings.RepositoriesFileApi, "delete", 202, repo.pulp_href)


@pytest.mark.parallel
def test_role_management(gen_users, file_bindings, file_repository_factory, try_action):
    """Check that role management apis."""
    alice, bob, charlie = gen_users("filerepository")
    with bob:
        href = file_repository_factory().pulp_href
    # Permission check testing
    aperm_response = try_action(
        alice, file_bindings.RepositoriesFileApi, "my_permissions", 200, href
    )
    assert aperm_response.permissions == []
    bperm_response = try_action(bob, file_bindings.RepositoriesFileApi, "my_permissions", 200, href)
    assert len(bperm_response.permissions) > 0
    try_action(charlie, file_bindings.RepositoriesFileApi, "my_permissions", 404, href)

    # Add "viewer" role testing
    nested_role = {"users": [charlie.username], "role": "file.filerepository_viewer"}
    try_action(
        alice, file_bindings.RepositoriesFileApi, "add_role", 403, href, nested_role=nested_role
    )
    try_action(
        charlie, file_bindings.RepositoriesFileApi, "add_role", 404, href, nested_role=nested_role
    )
    try_action(
        bob, file_bindings.RepositoriesFileApi, "add_role", 201, href, nested_role=nested_role
    )

    # Permission check testing again
    cperm_response = try_action(
        charlie, file_bindings.RepositoriesFileApi, "my_permissions", 200, href
    )
    assert len(cperm_response.permissions) == 1

    # Remove "viewer" role testing
    try_action(
        alice, file_bindings.RepositoriesFileApi, "remove_role", 403, href, nested_role=nested_role
    )
    try_action(
        charlie,
        file_bindings.RepositoriesFileApi,
        "remove_role",
        403,
        href,
        nested_role=nested_role,
    )
    try_action(
        bob, file_bindings.RepositoriesFileApi, "remove_role", 201, href, nested_role=nested_role
    )

    # Permission check testing one more time
    try_action(charlie, file_bindings.RepositoriesFileApi, "my_permissions", 404, href)


def test_content_apis(
    file_bindings,
    gen_users,
    file_repository_factory,
    file_remote_factory,
    file_fixture_server,
    basic_manifest_path,
    monitor_task,
    try_action,
    random_artifact,
):
    """Check content listing, scoping and upload APIs."""
    alice, bob, charlie = gen_users()
    aresponse = try_action(alice, file_bindings.ContentFilesApi, "list", 200)
    bresponse = try_action(bob, file_bindings.ContentFilesApi, "list", 200)
    cresponse = try_action(charlie, file_bindings.ContentFilesApi, "list", 200)

    assert aresponse.count == bresponse.count == cresponse.count == 0

    alice, bob, charlie = gen_users(["filerepository"])
    repo = file_repository_factory()
    remote = file_remote_factory(manifest_path=basic_manifest_path, policy="on_demand")
    monitor_task(
        file_bindings.RepositoriesFileApi.sync(repo.pulp_href, {"remote": remote.pulp_href}).task
    )

    aresponse = try_action(alice, file_bindings.ContentFilesApi, "list", 200)
    bresponse = try_action(bob, file_bindings.ContentFilesApi, "list", 200)
    cresponse = try_action(charlie, file_bindings.ContentFilesApi, "list", 200)

    assert aresponse.count > bresponse.count
    assert bresponse.count == cresponse.count == 0

    nested_role = {"users": [charlie.username], "role": "file.filerepository_viewer"}
    file_bindings.RepositoriesFileApi.add_role(repo.pulp_href, nested_role)

    cresponse = try_action(charlie, file_bindings.ContentFilesApi, "list", 200)
    assert cresponse.count > bresponse.count

    # This might need to change if we change Artifact's default upload policy
    body = {"artifact": random_artifact.pulp_href}
    try_action(alice, file_bindings.ContentFilesApi, "create", 400, "1.iso", **body)
    body["repository"] = repo.pulp_href
    try_action(bob, file_bindings.ContentFilesApi, "create", 403, "1.iso", **body)
    try_action(charlie, file_bindings.ContentFilesApi, "create", 403, "1.iso", **body)

    nested_role = {"users": [charlie.username], "role": "file.filerepository_owner"}
    file_bindings.RepositoriesFileApi.add_role(repo.pulp_href, nested_role)
    try_action(charlie, file_bindings.ContentFilesApi, "create", 202, "1.iso", **body)


@pytest.mark.parallel
def test_repository_apis(
    file_bindings,
    gen_users,
    file_repository_factory,
    file_remote_factory,
    try_action,
    basic_manifest_path,
):
    """Test repository specific actions, Modify & Sync."""
    alice, bob, charlie = gen_users(["filerepository", "fileremote"])
    # Sync tests
    with bob:
        bob_remote = file_remote_factory(manifest_path=basic_manifest_path, policy="on_demand")
        repo = file_repository_factory(remote=bob_remote.pulp_href)
    body = {"remote": bob_remote.pulp_href}
    try_action(alice, file_bindings.RepositoriesFileApi, "sync", 403, repo.pulp_href, body)
    try_action(bob, file_bindings.RepositoriesFileApi, "sync", 202, repo.pulp_href, body)
    # Try syncing without specifying a remote
    try_action(bob, file_bindings.RepositoriesFileApi, "sync", 202, repo.pulp_href, {})
    try_action(charlie, file_bindings.RepositoriesFileApi, "sync", 404, repo.pulp_href, body)
    # Modify tests
    try_action(alice, file_bindings.RepositoriesFileApi, "modify", 403, repo.pulp_href, {})
    try_action(bob, file_bindings.RepositoriesFileApi, "modify", 202, repo.pulp_href, {})
    try_action(charlie, file_bindings.RepositoriesFileApi, "modify", 404, repo.pulp_href, {})


@pytest.mark.parallel
def test_repository_version_repair(
    file_bindings,
    gen_users,
    file_repository_factory,
    try_action,
):
    """Test the repository version repair action"""
    alice, bob, charlie = gen_users("filerepository")
    with bob:
        repo = file_repository_factory()
        ver_href = repo.latest_version_href
    body = {"verify_checksums": True}
    try_action(alice, file_bindings.RepositoriesFileVersionsApi, "repair", 403, ver_href, body)
    try_action(bob, file_bindings.RepositoriesFileVersionsApi, "repair", 202, ver_href, body)
    try_action(charlie, file_bindings.RepositoriesFileVersionsApi, "repair", 403, ver_href, body)


@pytest.mark.parallel
def test_acs_apis(
    file_bindings,
    gen_users,
    file_remote_factory,
    monitor_task,
    try_action,
    basic_manifest_path,
):
    """Test acs refresh action."""
    alice, bob, charlie = gen_users(["filealternatecontentsource", "fileremote"])
    with bob:
        remote = file_remote_factory(manifest_path=basic_manifest_path, policy="on_demand")
        body = {"name": str(uuid.uuid4()), "remote": remote.pulp_href}
        acs = file_bindings.AcsFileApi.create(body)
    # Test that only bob can do the refresh action
    try_action(alice, file_bindings.AcsFileApi, "refresh", 403, acs.pulp_href)
    try_action(bob, file_bindings.AcsFileApi, "refresh", 202, acs.pulp_href)
    try_action(charlie, file_bindings.AcsFileApi, "refresh", 404, acs.pulp_href)

    monitor_task(file_bindings.AcsFileApi.delete(acs.pulp_href).task)


@pytest.mark.parallel
def test_object_creation(
    file_bindings,
    gen_users,
    file_repository_factory,
    monitor_task,
    try_action,
):
    """Test that objects can only be created when having all the required permissions."""
    alice, bob, charlie = gen_users(["filerepository", "filepublication", "filedistribution"])
    admin_repo = file_repository_factory()
    with bob:
        repo = file_repository_factory()
    try_action(
        bob, file_bindings.PublicationsFileApi, "create", 403, {"repository": admin_repo.pulp_href}
    )
    pub_from_repo_version = try_action(
        bob,
        file_bindings.PublicationsFileApi,
        "create",
        202,
        {"repository_version": repo.latest_version_href},
    )
    assert pub_from_repo_version.created_resources[0] is not None
    pub = try_action(
        bob, file_bindings.PublicationsFileApi, "create", 202, {"repository": repo.pulp_href}
    )
    pub = pub.created_resources[0]
    try_action(
        bob,
        file_bindings.DistributionsFileApi,
        "create",
        403,
        {
            "repository": admin_repo.pulp_href,
            "name": str(uuid.uuid4()),
            "base_path": str(uuid.uuid4()),
        },
    )
    dis = try_action(
        bob,
        file_bindings.DistributionsFileApi,
        "create",
        202,
        {
            "publication": pub,
            "name": str(uuid.uuid4()),
            "base_path": str(uuid.uuid4()),
        },
    ).created_resources[0]
    admin_body = {
        "repository": admin_repo.pulp_href,
        "publication": None,
        "name": str(uuid.uuid4()),
        "base_path": str(uuid.uuid4()),
    }
    bob_body = {
        "repository": repo.pulp_href,
        "publication": None,
        "name": str(uuid.uuid4()),
        "base_path": str(uuid.uuid4()),
    }
    try_action(bob, file_bindings.DistributionsFileApi, "partial_update", 403, dis, admin_body)
    try_action(bob, file_bindings.DistributionsFileApi, "partial_update", 202, dis, bob_body)
    monitor_task(file_bindings.DistributionsFileApi.delete(dis).task)
