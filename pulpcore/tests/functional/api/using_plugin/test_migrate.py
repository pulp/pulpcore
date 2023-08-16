import pytest
import json
import shutil

from pathlib import Path
from pulpcore.client.pulpcore import ApiException


@pytest.mark.parallel
def test_migrate_bad_settings(pulpcore_bindings, domain_factory):
    """Test that backend settings are validated before launching the task."""
    domain = domain_factory(storage_class="pulpcore.app.models.storage.FileSystem")
    settings = {}
    # Test with missing field
    body = {"storage_class": "pulpcore.app.models.storage.FileSystem", "storage_settings": settings}
    kwargs = {"pulp_domain": domain.name}
    with pytest.raises(ApiException) as e:
        pulpcore_bindings.DomainsApi.migrate(body, **kwargs)
    error_body = json.loads(e.value.body)
    assert "storage_settings" in error_body
    assert {"location": ["This field is required."]} == error_body["storage_settings"]
    # Test with unexpected field
    settings["location"] = "/var/lib/pulp/media"
    settings["random"] = "random"
    body["storage_settings"] = settings
    with pytest.raises(ApiException) as e:
        pulpcore_bindings.DomainsApi.migrate(body, **kwargs)
    assert e.value.status == 400
    error_body = json.loads(e.value.body)
    assert "storage_settings" in error_body
    assert "Unexpected field" in error_body["storage_settings"].values()


@pytest.mark.parallel
def test_migrate_default_domain(pulpcore_bindings, pulp_domain_enabled):
    """Test the default domain can not be migrated."""
    domain = pulpcore_bindings.DomainsApi.list(name="default").results[0]

    kwargs = {}
    if pulp_domain_enabled:
        kwargs["pulp_domain"] = domain.name
    with pytest.raises(pulpcore_bindings.ApiException) as e:
        pulpcore_bindings.DomainsApi.migrate({}, **kwargs)
    assert e.value.status == 400
    assert "Default domain can not be migrated" in e.value.body


@pytest.mark.parallel
def test_migrate_domain(
    pulpcore_bindings,
    domain_factory,
    backend_settings_factory,
    monitor_task,
    random_artifact_factory,
):
    """Test migrating from a domain."""
    domain = domain_factory()
    domain_id = domain.pulp_href.split("/")[-2]
    artifacts = [random_artifact_factory(pulp_domain=domain.name) for _ in range(3)]
    old_storage, old_settings = backend_settings_factory()

    body = {
        "storage_class": "pulpcore.app.models.storage.FileSystem",
        "storage_settings": {"location": "/var/lib/pulp/media"},
    }
    task = monitor_task(pulpcore_bindings.DomainsApi.migrate(body, pulp_domain=domain.name).task)

    # Check that the progress reports and 'done's are right
    reports = task.progress_reports
    assert len(reports) == 2
    assert {3, 1} == {r.done for r in reports}

    # Check that the domain's storage settings was updated
    domain = pulpcore_bindings.DomainsApi.read(domain.pulp_href)
    assert domain.storage_class == "pulpcore.app.models.storage.FileSystem"
    assert domain.storage_settings["location"] == "/var/lib/pulp/media"

    # Check that the files were actually moved
    expected_paths = set()
    for artifact in artifacts:
        a = f"/var/lib/pulp/media/artifact/{domain_id}/{artifact.sha256[0:2]}/{artifact.sha256[2:]}"
        expected_paths.add(a)
    found_paths = {str(p) for p in Path(f"/var/lib/pulp/media/artifact/{domain_id}").glob("*/*")}

    # Perform cleanup before final assert
    shutil.rmtree(f"/var/lib/pulp/media/artifact/{domain_id}")
    # Restore original domain settings without migrating
    body = {"storage_class": old_storage, "storage_settings": old_settings}
    monitor_task(pulpcore_bindings.DomainsApi.partial_update(domain.pulp_href, body).task)

    assert len(expected_paths) == 3
    assert expected_paths == found_paths


@pytest.mark.parallel
def test_migrate_empty_domain(
    pulpcore_bindings, domain_factory, backend_settings_factory, monitor_task
):
    """Test migrating works even when there are no artifacts."""
    domain = domain_factory()

    storage, settings = backend_settings_factory()
    body = {"storage_class": storage, "storage_settings": settings}
    task = monitor_task(pulpcore_bindings.DomainsApi.migrate(body, pulp_domain=domain.name).task)

    reports = task.progress_reports
    assert len(reports) == 2
    for report in reports:
        if report.message == "Migrating Artifacts":
            assert report.total == 0
            assert report.done == 0
