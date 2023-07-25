import pytest
import uuid

from pulpcore.tests.functional.utils import PulpTaskGroupError


@pytest.mark.parallel
def test_replication(
    domain_factory,
    bindings_cfg,
    upstream_pulp_api_client,
    monitor_task_group,
    pulp_settings,
    gen_object_with_cleanup,
):
    # This test assures that an Upstream Pulp can be created in a non-default domain and that this
    # Upstream Pulp configuration can be used to execute the replicate task.

    # Create a non-default domain
    non_default_domain = domain_factory()

    # Create an Upstream Pulp in the non-default domain
    upstream_pulp_body = {
        "name": str(uuid.uuid4()),
        "base_url": bindings_cfg.host,
        "api_root": pulp_settings.API_ROOT,
        "domain": "default",
        "username": bindings_cfg.username,
        "password": bindings_cfg.password,
    }
    upstream_pulp = gen_object_with_cleanup(
        upstream_pulp_api_client, upstream_pulp_body, pulp_domain=non_default_domain.name
    )
    # Run the replicate task and assert that all tasks successfully complete.
    response = upstream_pulp_api_client.replicate(upstream_pulp.pulp_href)
    task_group = monitor_task_group(response.task_group)
    for task in task_group.tasks:
        assert task.state == "completed"


@pytest.mark.parallel
def test_replication_with_wrong_ca_cert(
    domain_factory,
    bindings_cfg,
    upstream_pulp_api_client,
    monitor_task_group,
    pulp_settings,
    gen_object_with_cleanup,
    tasks_api_client,
):
    # This test assures that setting ca_cert on an Upstream Pulp causes that CA bundle to be used
    # to verify the certificate presented by the Upstream Pulp's REST API. The replication tasks
    # are expected to fail.

    if not bindings_cfg.host.startswith("https"):
        pytest.skip("HTTPS is not enabled for Pulp's API.")

    # Create a non-default domain
    non_default_domain = domain_factory()

    # Create an Upstream Pulp in the non-default domain
    upstream_pulp_body = {
        "name": str(uuid.uuid4()),
        "base_url": bindings_cfg.host,
        "api_root": pulp_settings.API_ROOT,
        "domain": "default",
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
        upstream_pulp_api_client, upstream_pulp_body, pulp_domain=non_default_domain.name
    )
    # Run the replicate task and assert that it fails with SSLError
    with pytest.raises(PulpTaskGroupError) as e:
        response = upstream_pulp_api_client.replicate(upstream_pulp.pulp_href)
        monitor_task_group(response.task_group)

    task = tasks_api_client.read(e.value.task_group.tasks[0].pulp_href)
    assert "SSLError" in task.error["description"]

    # Update Upstream Pulp with tls_validation=False
    upstream_pulp_api_client.partial_update(upstream_pulp.pulp_href, {"tls_validation": False})

    # Run the replicate task again and assert that all tasks successfully complete.
    response = upstream_pulp_api_client.replicate(upstream_pulp.pulp_href)
    task_group = monitor_task_group(response.task_group)
    for task in task_group.tasks:
        assert task.state == "completed"
