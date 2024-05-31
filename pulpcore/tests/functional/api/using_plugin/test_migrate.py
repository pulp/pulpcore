import pytest
import json
import shutil

from pathlib import Path
from pulpcore.client.pulpcore import ApiException


@pytest.mark.parallel
def test_migrate_bad_settings(domains_api_client, domain_factory):
    """Test that backend settings are validated before launching the task."""
    domain = domain_factory(storage_class="pulpcore.app.models.storage.FileSystem")
    settings = {}
    # Test with missing field
    body = {"storage_class": "pulpcore.app.models.storage.FileSystem", "storage_settings": settings}
    kwargs = {"pulp_domain": domain.name}
    with pytest.raises(ApiException) as e:
        domains_api_client.migrate(body, **kwargs)
    error_body = json.loads(e.value.body)
    assert "storage_settings" in error_body
    assert {"location": ["This field is required."]} == error_body["storage_settings"]
    # Test with unexpected field
    settings["location"] = "/var/lib/pulp/media"
    settings["random"] = "random"
    body["storage_settings"] = settings
    with pytest.raises(ApiException) as e:
        domains_api_client.migrate(body, **kwargs)
    assert e.value.status == 400
    error_body = json.loads(e.value.body)
    assert "storage_settings" in error_body
    assert "Unexpected field" in error_body["storage_settings"].values()


def test_migrate_default_domain(domains_api_client, monitor_task, pulp_domain_enabled):
    """Test migrating from the default domain."""
    domain = domains_api_client.list(name="default").results[0]

    # Perform in-place migration, this should have no effect on the domain
    kwargs = {}
    if pulp_domain_enabled:
        kwargs["pulp_domain"] = domain.name
    task = monitor_task(domains_api_client.migrate({}, **kwargs).task)

    reports = task.progress_reports
    assert len(reports) == 2
    msgs = {
        "Migrating Artifacts",
        "Update Domain(default)'s Backend Settings",
    }
    assert msgs == {pr.message for pr in reports}

    # Default domain shouldn't be updated even after the migration
    domain2 = domains_api_client.list(name="default").results[0]
    assert domain == domain2


@pytest.mark.parallel
def test_migrate_domain(
    domain_factory,
    domains_api_client,
    backend_settings_factory,
    monitor_task,
    random_artifact_factory,
):
    """Test migrating from a domain."""
    domain = domain_factory()
    artifacts = [random_artifact_factory(pulp_domain=domain.name) for _ in range(3)]
    old_storage, old_settings = backend_settings_factory()

    body = {
        "storage_class": "pulpcore.app.models.storage.FileSystem",
        "storage_settings": {"location": "/var/lib/pulp/media"},
    }
    task = monitor_task(domains_api_client.migrate(body, pulp_domain=domain.name).task)

    # Check that the progress reports and 'done's are right
    reports = task.progress_reports
    assert len(reports) == 2
    assert {3, 1} == {r.done for r in reports}

    # Check that the domain's storage settings was updated
    domain2 = domains_api_client.read(domain.pulp_href)
    assert domain2.storage_class == "pulpcore.app.models.storage.FileSystem"
    assert domain2.storage_settings["location"] == "/var/lib/pulp/media"

    # Check that the files were actually moved
    domain_id = domain.pulp_href.split("/")[-2]
    expected_paths = set()
    for artifact in artifacts:
        a = f"/var/lib/pulp/media/artifact/{domain_id}/{artifact.sha256[0:2]}/{artifact.sha256[2:]}"
        expected_paths.add(a)
    found_paths = {str(p) for p in Path(f"/var/lib/pulp/media/artifact/{domain_id}").glob("*/*")}

    # Perform cleanup before final assert
    shutil.rmtree(f"/var/lib/pulp/media/artifact/{domain_id}")
    # Restore original domain settings
    body = {"storage_class": old_storage, "storage_settings": old_settings}
    monitor_task(domains_api_client.partial_update(domain.pulp_href, body).task)

    assert len(expected_paths) == 3
    assert expected_paths == found_paths


@pytest.mark.parallel
def test_migrate_empty_domain(
    domain_factory, domains_api_client, backend_settings_factory, monitor_task
):
    """Test migrating works even when there are no artifacts."""
    domain = domain_factory()

    storage, settings = backend_settings_factory()
    body = {"storage_class": storage, "storage_settings": settings}
    task = monitor_task(domains_api_client.migrate(body, pulp_domain=domain.name).task)

    reports = task.progress_reports
    assert len(reports) == 2
    for report in reports:
        if report.message == "Migrating Artifacts":
            assert report.total == 0
            assert report.done == 0
