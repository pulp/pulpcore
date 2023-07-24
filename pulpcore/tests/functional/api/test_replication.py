import pytest
import uuid


@pytest.mark.parallel
def test_replication(
    domain_factory,
    domains_api_client,
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
        "base_url": domains_api_client.api_client.configuration.host,
        "api_root": pulp_settings.API_ROOT,
        "domain": "default",
        "username": domains_api_client.api_client.configuration.username,
        "password": domains_api_client.api_client.configuration.password,
    }
    upstream_pulp = gen_object_with_cleanup(
        upstream_pulp_api_client, upstream_pulp_body, pulp_domain=non_default_domain.name
    )
    # Run the replicate task and assert that all tasks successfully complete.
    response = upstream_pulp_api_client.replicate(upstream_pulp.pulp_href)
    task_group = monitor_task_group(response.task_group)
    for task in task_group.tasks:
        assert task.state == "completed"
