import pytest
import uuid

from pulpcore.client.pulpcore import ApiException
from pulpcore.client.pulpcore import AsyncOperationResponse
from pulpcore.client.pulp_file import RepositorySyncURL

from pulpcore.tests.functional.utils import PulpTaskGroupError, generate_iso


@pytest.mark.parallel
def test_replication(
    domain_factory,
    bindings_cfg,
    pulpcore_bindings,
    monitor_task_group,
    pulp_settings,
    gen_object_with_cleanup,
):
    # This test assures that an Upstream Pulp can be created in a non-default domain and that this
    # Upstream Pulp configuration can be used to execute the replicate task.

    # Create a non-default domain
    non_default_domain = domain_factory()

    # Create a domain to replicate from
    source_domain = domain_factory()

    # Create an Upstream Pulp in the non-default domain
    upstream_pulp_body = {
        "name": str(uuid.uuid4()),
        "base_url": bindings_cfg.host,
        "api_root": pulp_settings.API_ROOT,
        "domain": source_domain.name,
        "username": bindings_cfg.username,
        "password": bindings_cfg.password,
    }
    upstream_pulp = gen_object_with_cleanup(
        pulpcore_bindings.UpstreamPulpsApi, upstream_pulp_body, pulp_domain=non_default_domain.name
    )
    # Run the replicate task and assert that all tasks successfully complete.
    response = pulpcore_bindings.UpstreamPulpsApi.replicate(upstream_pulp.pulp_href)
    task_group = monitor_task_group(response.task_group)
    for task in task_group.tasks:
        assert task.state == "completed"


@pytest.mark.parallel
def test_replication_idempotence(
    domain_factory,
    bindings_cfg,
    pulpcore_bindings,
    file_bindings,
    monitor_task,
    monitor_task_group,
    pulp_settings,
    add_to_cleanup,
    gen_object_with_cleanup,
    file_distribution_factory,
    file_publication_factory,
    file_repository_factory,
    tmp_path,
):
    # This test assures that an Upstream Pulp can be created in a non-default domain and that this
    # Upstream Pulp configuration can be used to execute the replicate task.

    # Create a domain to replicate from
    source_domain = domain_factory()

    # Add stuff to it
    repository = file_repository_factory(pulp_domain=source_domain.name)
    file_path = tmp_path / "file.txt"
    file_path.write_text("DEADBEEF")
    monitor_task(
        file_bindings.ContentFilesApi.create(
            file=file_path,
            relative_path="file.txt",
            repository=repository.pulp_href,
            pulp_domain=source_domain.name,
        ).task
    )
    publication = file_publication_factory(
        pulp_domain=source_domain.name, repository=repository.pulp_href
    )
    file_distribution_factory(pulp_domain=source_domain.name, publication=publication.pulp_href)

    # Create a domain as replica
    replica_domain = domain_factory()

    # Create an Upstream Pulp in the non-default domain
    upstream_pulp_body = {
        "name": str(uuid.uuid4()),
        "base_url": bindings_cfg.host,
        "api_root": pulp_settings.API_ROOT,
        "domain": source_domain.name,
        "username": bindings_cfg.username,
        "password": bindings_cfg.password,
    }
    upstream_pulp = gen_object_with_cleanup(
        pulpcore_bindings.UpstreamPulpsApi, upstream_pulp_body, pulp_domain=replica_domain.name
    )
    # Run the replicate task and assert that all tasks successfully complete.
    response = pulpcore_bindings.UpstreamPulpsApi.replicate(upstream_pulp.pulp_href)
    monitor_task_group(response.task_group)

    for api_client in (
        file_bindings.DistributionsFileApi,
        file_bindings.RemotesFileApi,
        file_bindings.RepositoriesFileApi,
    ):
        result = api_client.list(pulp_domain=replica_domain.name)
        for item in result.results:
            add_to_cleanup(api_client, item)

    for api_client in (
        file_bindings.DistributionsFileApi,
        file_bindings.RemotesFileApi,
        file_bindings.RepositoriesFileApi,
        file_bindings.ContentFilesApi,
    ):
        result = api_client.list(pulp_domain=replica_domain.name)
        assert result.count == 1

    # Now replicate backwards

    upstream_pulp_body = {
        "name": str(uuid.uuid4()),
        "base_url": bindings_cfg.host,
        "api_root": pulp_settings.API_ROOT,
        "domain": replica_domain.name,
        "username": bindings_cfg.username,
        "password": bindings_cfg.password,
    }
    upstream_pulp = gen_object_with_cleanup(
        pulpcore_bindings.UpstreamPulpsApi, upstream_pulp_body, pulp_domain=source_domain.name
    )
    # Run the replicate task and assert that all tasks successfully complete.
    response = pulpcore_bindings.UpstreamPulpsApi.replicate(upstream_pulp.pulp_href)
    monitor_task_group(response.task_group)

    for api_client in (
        file_bindings.DistributionsFileApi,
        file_bindings.RemotesFileApi,
        file_bindings.RepositoriesFileApi,
    ):
        result = api_client.list(pulp_domain=replica_domain.name)
        for item in result.results:
            add_to_cleanup(api_client, item)


@pytest.mark.parallel
def test_replication_with_wrong_ca_cert(
    domain_factory,
    bindings_cfg,
    pulpcore_bindings,
    monitor_task_group,
    pulp_settings,
    gen_object_with_cleanup,
):
    # This test assures that setting ca_cert on an Upstream Pulp causes that CA bundle to be used
    # to verify the certificate presented by the Upstream Pulp's REST API. The replication tasks
    # are expected to fail.

    if not bindings_cfg.host.startswith("https"):
        pytest.skip("HTTPS is not enabled for Pulp's API.")

    # Create a non-default domain
    non_default_domain = domain_factory()

    # Create a domain to replicate from
    source_domain = domain_factory()

    # Create an Upstream Pulp in the non-default domain
    upstream_pulp_body = {
        "name": str(uuid.uuid4()),
        "base_url": bindings_cfg.host,
        "api_root": pulp_settings.API_ROOT,
        "domain": source_domain.name,
        "username": bindings_cfg.username,
        "password": bindings_cfg.password,
        "ca_cert": """-----BEGIN CERTIFICATE-----
MIIDyDCCArCgAwIBAgIJALMhZGyJtHXTMA0GCSqGSIb3DQEBCwUAMIGgMQswCQYD
VQQGEwJTRzEUMBIGA1UECAwLTmV3IFlvcmsxFTATBgNVBAcMDERlZmF1bHQgQ2l0
eTEUMBIGA1UECgwLSW50ZXJuZXQxFDASBgNVBAsMC0RldmljZXMgVGVjaG5vbG9n
MRYwFAYDVQQDDA1leGFtcGxlLmNvbTEfMB0GCSqGSIb3DQEJARYQYWRtaW5AaW50
ZXJuZXQuY29tMB4XDTE5MTIwNjAyMTIwM1oXDTIwMTIwNDAyMTIwM1owgaAxCzAJ
BgNVBAYTAlNHMRQwEgYDVQQIDAtOZXcgWW9yazEVMBMGA1UEBwwMRGVmYXVsdCBD
aXR5MRQwEgYDVQQKDAtJbnRlcm5ldDEUMBIGA1UECwwLRGV2aWNlcyBUZWNobm9s
b2cxFjAUBgNVBAMMDWV4YW1wbGUuY29tMR8wHQYJKoZIhvcNAQkBFhBhZG1pbkBp
bnRlcm5ldC5jb20wggEiMA0GCSqGSIb3DQEBAQUAA4IBDwAwggEKAoIBAQCy27Nm
oJNlD8F4LmffMk8mXL3i/MTc9/Cj7xXVieNWm+cyz2BkSi/XAhntJjsfWjLCwvcd
9femwRcEUKbDKZVa84Yr4MRb/i6wtMdZt6qOxTPlldM7eF7QrAK1wBqjMxHZl5uL
ncBGBAPs4o1I7KUoQalnSm7FLZzPV60TQHcdmMIRANFqZaJ0jb+vlrxL7vJ7Yt5O
SsfHir2Bn/Z62c3ERb7uE5RQvzU1erVd0C15zYZYfNB7BglwQLpISIw9ReLrg6bw
j3gRQ3yqaXe5ZuayMWUG8JzyDEY5j3eHYqHK1aWhPTMImJOFRrBuj3cbW8JLPOf0
EfJ6xqSgk2iVAgMBAAGjUDBOMB0GA1UdDgQWBBS7Exn/viOvOS93WhmM8bLlm5U/
xTAPBgNVHRMBAf8EBTADAQH/MB8GA1UdIwQYMBaAFLsTGf++I682vTd4ZjPGy5Zu
VP8TAfBgNVHSMEGDAWgBRjURbn0MwB+L8va9VSUWektp7QaDANBgkqhkiG9w0BAQsF
AAOCAQEAHIrr6D9T32H3i5rvsHH6ZZ+2iNDPmI2qN8LOF9SzNbs5KLRAspOARaOC
GIE99WpK0QJe+9dPcmK6oPvRlU14eck+o61BhC9E6BuvV3Vv00GcAh/rqUbvkq4a
L/7ZI2P5pXex51bNGHt+Je9+6+o3sjn0cc5Itskf56Fh5hTHbrEfTh/f1wLJ3MjK
e5y57vC9A7dIfa3dKcc3nv3EzZ2L6IzDC9QunMXD1p+cID+x8sD5D7gs2Y65SvFw
dzcy5UufxW7J3ELZ9MJoKF3Y0npqRP2RW07s0CDupkFbPF5zKStM/6Ilzz6JJesq
SQiVeWgI8fDCpQ/6KiI7F3el8nEc5w==
-----END CERTIFICATE-----
""",
    }
    upstream_pulp = gen_object_with_cleanup(
        pulpcore_bindings.UpstreamPulpsApi, upstream_pulp_body, pulp_domain=non_default_domain.name
    )
    # Run the replicate task and assert that it fails with SSLError
    with pytest.raises(PulpTaskGroupError) as e:
        response = pulpcore_bindings.UpstreamPulpsApi.replicate(upstream_pulp.pulp_href)
        monitor_task_group(response.task_group)

    task = pulpcore_bindings.TasksApi.read(e.value.task_group.tasks[0].pulp_href)
    assert "SSLError" in task.error["description"]

    # Update Upstream Pulp with tls_validation=False
    pulpcore_bindings.UpstreamPulpsApi.partial_update(
        upstream_pulp.pulp_href, {"tls_validation": False}
    )

    # Run the replicate task again and assert that all tasks successfully complete.
    response = pulpcore_bindings.UpstreamPulpsApi.replicate(upstream_pulp.pulp_href)
    task_group = monitor_task_group(response.task_group)
    for task in task_group.tasks:
        assert task.state == "completed"


@pytest.mark.parallel
def test_replication_optimization(
    check_replication,
    domain_factory,
    bindings_cfg,
    pulpcore_bindings,
    pulp_settings,
    file_bindings,
    file_repository_factory,
    file_remote_factory,
    file_distribution_factory,
    file_publication_factory,
    basic_manifest_path,
    monitor_task,
    gen_object_with_cleanup,
    tmp_path,
):
    non_default_domain = domain_factory()
    source_domain = domain_factory()
    upstream_pulp_body = {
        "name": str(uuid.uuid4()),
        "base_url": bindings_cfg.host,
        "api_root": pulp_settings.API_ROOT,
        "domain": source_domain.name,
        "username": bindings_cfg.username,
        "password": bindings_cfg.password,
    }
    upstream_pulp = gen_object_with_cleanup(
        pulpcore_bindings.UpstreamPulpsApi, upstream_pulp_body, pulp_domain=non_default_domain.name
    )

    # sync a repository on the "remote" Pulp instance
    upstream_remote = file_remote_factory(
        pulp_domain=source_domain.name, manifest_path=basic_manifest_path, policy="immediate"
    )
    upstream_repository = file_repository_factory(pulp_domain=source_domain.name)

    repository_sync_data = RepositorySyncURL(remote=upstream_remote.pulp_href, mirror=True)
    response = file_bindings.RepositoriesFileApi.sync(
        upstream_repository.pulp_href, repository_sync_data
    )
    monitor_task(response.task)
    upstream_repository = file_bindings.RepositoriesFileApi.read(upstream_repository.pulp_href)
    upstream_publication = file_publication_factory(
        pulp_domain=source_domain.name, repository_version=upstream_repository.latest_version_href
    )
    upstream_distribution = file_distribution_factory(
        pulp_domain=source_domain.name, publication=upstream_publication.pulp_href
    )

    # replicate the "remote" instance and ensure the sync task is run
    replication_timestamp = check_replication(
        upstream_pulp, upstream_distribution, non_default_domain, None
    )

    # replicate the "remote" instance again to check if the sync task was skipped
    replication_timestamp = check_replication(
        upstream_pulp,
        upstream_distribution,
        non_default_domain,
        replication_timestamp,
        should_run_sync_task=False,
    )

    # upload new content to the repository on the "remote" Pulp instance (creating a new version)
    filename = tmp_path / str(uuid.uuid4())
    generate_iso(filename)
    relative_path = "1.iso"

    response = file_bindings.ContentFilesApi.create(
        relative_path,
        file=filename,
        repository=upstream_repository.pulp_href,
        pulp_domain=source_domain.name,
    )
    monitor_task(response.task)
    upstream_repository = file_bindings.RepositoriesFileApi.read(upstream_repository.pulp_href)
    upstream_publication = file_publication_factory(
        pulp_domain=source_domain.name, repository_version=upstream_repository.latest_version_href
    )
    response = file_bindings.DistributionsFileApi.partial_update(
        upstream_distribution.pulp_href,
        {"publication": upstream_publication.pulp_href},
    )
    monitor_task(response.task)

    # replicate the "remote" instance again to check if the sync task had been executed
    check_replication(
        upstream_pulp, upstream_distribution, non_default_domain, replication_timestamp
    )


@pytest.fixture
def check_replication(pulpcore_bindings, file_bindings, monitor_task_group):
    def _check_replication(
        upstream_pulp,
        upstream_distribution,
        local_domain,
        old_replication,
        should_run_sync_task=True,
    ):
        response = pulpcore_bindings.UpstreamPulpsApi.replicate(upstream_pulp.pulp_href)
        # check if the replication succeeded
        task_group = monitor_task_group(response.task_group)
        for task in task_group.tasks:
            assert task.state == "completed"

        # check if the optimization took a place
        if should_run_sync_task:
            assert any("sync" in task.name for task in task_group.tasks), task_group.tasks
        else:
            assert all("sync" not in task.name for task in task_group.tasks), task_group.tasks

        upstream_distribution = file_bindings.DistributionsFileApi.read(
            upstream_distribution.pulp_href
        )
        distribution = file_bindings.DistributionsFileApi.list(
            name=upstream_distribution.name,
            pulp_domain=local_domain.name,
        ).results[0]

        upstream_pulp = pulpcore_bindings.UpstreamPulpsApi.read(upstream_pulp.pulp_href)
        # check if the timestamps of the replica has changed
        if old_replication is None:
            assert upstream_pulp.last_replication is not None
        else:
            assert upstream_pulp.last_replication > old_replication

        # check if the content was correctly replicated
        local_version = file_bindings.RepositoriesFileApi.read(
            distribution.repository
        ).latest_version_href
        local_present = file_bindings.RepositoriesFileVersionsApi.read(
            local_version
        ).content_summary.present
        upstream_version = file_bindings.PublicationsFileApi.read(
            upstream_distribution.publication
        ).repository_version
        upstream_present = file_bindings.RepositoriesFileVersionsApi.read(
            upstream_version
        ).content_summary.present

        assert upstream_present["file.file"]["count"] == local_present["file.file"]["count"]

        return upstream_pulp.last_replication

    return _check_replication


@pytest.fixture()
def gen_users(gen_user):
    """Returns a user generator function for the tests."""

    def _gen_users(role_names=list()):
        if isinstance(role_names, str):
            role_names = [role_names]
        viewer_roles = [f"core.{role}_viewer" for role in role_names]
        creator_roles = [f"core.{role}_creator" for role in role_names]
        user_roles = [f"core.{role}_user" for role in role_names]
        alice = gen_user(model_roles=viewer_roles)
        bob = gen_user(model_roles=creator_roles)
        charlie = gen_user()
        dean = gen_user(model_roles=user_roles)
        return alice, bob, charlie, dean

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


@pytest.mark.parallel
def test_replicate_rbac(
    gen_users,
    try_action,
    domain_factory,
    bindings_cfg,
    pulpcore_bindings,
    pulp_settings,
    gen_object_with_cleanup,
):
    alice, bob, charlie, dean = gen_users(["upstreampulp"])
    # Create a non-default domain
    non_default_domain = domain_factory()

    with bob:
        upstream_pulp_body = {
            "name": str(uuid.uuid4()),
            "base_url": bindings_cfg.host,
            "api_root": pulp_settings.API_ROOT,
            "domain": "default",
            "username": bindings_cfg.username,
            "password": bindings_cfg.password,
        }
        upstream_pulp = gen_object_with_cleanup(
            pulpcore_bindings.UpstreamPulpsApi,
            upstream_pulp_body,
            pulp_domain=non_default_domain.name,
        )

    # Assert that Alice (upstream pulp viewer) gets a 403
    try_action(alice, pulpcore_bindings.UpstreamPulpsApi, "replicate", 403, upstream_pulp.pulp_href)

    # Assert that B (upstream pulp owner) gets a 202
    try_action(bob, pulpcore_bindings.UpstreamPulpsApi, "replicate", 202, upstream_pulp.pulp_href)

    # Assert that Charlie (no role) get a 404
    try_action(
        charlie, pulpcore_bindings.UpstreamPulpsApi, "replicate", 404, upstream_pulp.pulp_href
    )

    # Assert that Dean can run replication
    try_action(dean, pulpcore_bindings.UpstreamPulpsApi, "replicate", 202, upstream_pulp.pulp_href)

    # Assert that Dean can view the upstream pulp
    try_action(dean, pulpcore_bindings.UpstreamPulpsApi, "read", 200, upstream_pulp.pulp_href)

    # Assert that Dean can't update the upstream pulp
    try_action(
        dean, pulpcore_bindings.UpstreamPulpsApi, "partial_update", 403, upstream_pulp.pulp_href, {}
    )


@pytest.fixture
def populate_upstream(
    domain_factory,
    file_bindings,
    file_repository_factory,
    file_remote_factory,
    file_distribution_factory,
    write_3_iso_file_fixture_data_factory,
    monitor_task,
):
    def _populate_upstream(number):
        upstream_domain = domain_factory()
        tasks = []
        for i in range(number):
            repo = file_repository_factory(pulp_domain=upstream_domain.name, autopublish=True)
            fix = write_3_iso_file_fixture_data_factory(str(i))
            remote = file_remote_factory(pulp_domain=upstream_domain.name, manifest_path=fix)
            body = {"remote": remote.pulp_href}
            tasks.append(file_bindings.RepositoriesFileApi.sync(repo.pulp_href, body).task)
            file_distribution_factory(
                name=str(i),
                pulp_domain=upstream_domain.name,
                repository=repo.pulp_href,
                pulp_labels={"upstream": str(i), "even" if i % 2 == 0 else "odd": ""},
            )
        for t in tasks:
            monitor_task(t)
        return upstream_domain

    return _populate_upstream


@pytest.mark.parallel
def test_replicate_with_basic_q_select(
    domain_factory,
    populate_upstream,
    bindings_cfg,
    pulpcore_bindings,
    monitor_task_group,
    pulp_settings,
    gen_object_with_cleanup,
):
    """Test basic label select replication."""
    source_domain = populate_upstream(10)
    dest_domain = domain_factory()
    upstream_body = {
        "name": str(uuid.uuid4()),
        "base_url": bindings_cfg.host,
        "api_root": pulp_settings.API_ROOT,
        "domain": source_domain.name,
        "username": bindings_cfg.username,
        "password": bindings_cfg.password,
    }
    upstream = gen_object_with_cleanup(
        pulpcore_bindings.UpstreamPulpsApi, upstream_body, pulp_domain=dest_domain.name
    )
    # Run the replicate task and assert that all 10 repos got synced
    response = pulpcore_bindings.UpstreamPulpsApi.replicate(upstream.pulp_href)
    monitor_task_group(response.task_group)
    result = pulpcore_bindings.DistributionsApi.list(pulp_domain=dest_domain.name)
    assert result.count == 10

    # Update q_select to sync only 'even' repos
    body = {"q_select": "pulp_label_select='even'"}
    pulpcore_bindings.UpstreamPulpsApi.partial_update(upstream.pulp_href, body)
    response = pulpcore_bindings.UpstreamPulpsApi.replicate(upstream.pulp_href)
    monitor_task_group(response.task_group)
    result = pulpcore_bindings.DistributionsApi.list(pulp_domain=dest_domain.name)
    assert result.count == 5
    assert {d.name for d in result.results} == {"0", "2", "4", "6", "8"}

    # Update q_select to sync one 'upstream' repo
    body["q_select"] = "pulp_label_select='upstream=4'"
    pulpcore_bindings.UpstreamPulpsApi.partial_update(upstream.pulp_href, body)
    response = pulpcore_bindings.UpstreamPulpsApi.replicate(upstream.pulp_href)
    monitor_task_group(response.task_group)
    result = pulpcore_bindings.DistributionsApi.list(pulp_domain=dest_domain.name)
    assert result.count == 1
    assert result.results[0].name == "4"

    # Show that basic label select is ANDed together
    body["q_select"] = "pulp_label_select='even,upstream=0'"
    pulpcore_bindings.UpstreamPulpsApi.partial_update(upstream.pulp_href, body)
    response = pulpcore_bindings.UpstreamPulpsApi.replicate(upstream.pulp_href)
    monitor_task_group(response.task_group)
    result = pulpcore_bindings.DistributionsApi.list(pulp_domain=dest_domain.name)
    assert result.count == 1
    assert result.results[0].name == "0"


@pytest.mark.parallel
def test_replicate_with_complex_q_select(
    domain_factory,
    populate_upstream,
    bindings_cfg,
    pulpcore_bindings,
    monitor_task_group,
    pulp_settings,
    gen_object_with_cleanup,
):
    """Test complex q_select replication."""
    source_domain = populate_upstream(10)
    dest_domain = domain_factory()
    upstream_body = {
        "name": str(uuid.uuid4()),
        "base_url": bindings_cfg.host,
        "api_root": pulp_settings.API_ROOT,
        "domain": source_domain.name,
        "username": bindings_cfg.username,
        "password": bindings_cfg.password,
        "q_select": "pulp_label_select='upstream=1' OR pulp_label_select='upstream=2'",
    }
    upstream = gen_object_with_cleanup(
        pulpcore_bindings.UpstreamPulpsApi, upstream_body, pulp_domain=dest_domain.name
    )
    # Run the replicate task and assert that two repos got synced
    response = pulpcore_bindings.UpstreamPulpsApi.replicate(upstream.pulp_href)
    monitor_task_group(response.task_group)
    result = pulpcore_bindings.DistributionsApi.list(pulp_domain=dest_domain.name)
    assert result.count == 2
    assert {d.name for d in result.results} == {"1", "2"}

    # Test odds but not seven
    body = {"q_select": "pulp_label_select='odd' AND NOT pulp_label_select='upstream=7'"}
    pulpcore_bindings.UpstreamPulpsApi.partial_update(upstream.pulp_href, body)
    response = pulpcore_bindings.UpstreamPulpsApi.replicate(upstream.pulp_href)
    monitor_task_group(response.task_group)
    result = pulpcore_bindings.DistributionsApi.list(pulp_domain=dest_domain.name)
    assert result.count == 4
    assert {d.name for d in result.results} == {"1", "3", "5", "9"}

    # Test we error when trying to provide an invalid q expression
    body["q_select"] = "invalid='testing'"
    with pytest.raises(pulpcore_bindings.ApiException) as e:
        pulpcore_bindings.UpstreamPulpsApi.partial_update(upstream.pulp_href, body)
    assert e.value.status == 400
    assert e.value.body == '{"q_select":["Filter \'invalid\' does not exist."]}'

    body["q_select"] = "name='hi' AND"
    with pytest.raises(pulpcore_bindings.ApiException) as e:
        pulpcore_bindings.UpstreamPulpsApi.partial_update(upstream.pulp_href, body)
    assert e.value.status == 400
    assert e.value.body == '{"q_select":["Syntax error in expression."]}'
