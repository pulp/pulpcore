import pytest
import uuid
import json

from pulpcore.app import settings
from pulpcore.client.pulp_file import ApiException
from pulpcore.client.pulpcore import ApiException as CoreApiException
from pulpcore.client.pulpcore import Repair
from pulpcore.tests.functional.utils import generate_iso, download_file


pytestmark = pytest.mark.skipif(not settings.DOMAIN_ENABLED, reason="Domains not enabled.")


@pytest.mark.parallel
def test_object_creation(
    pulpcore_bindings,
    file_bindings,
    gen_object_with_cleanup,
    file_remote_factory,
    basic_manifest_path,
):
    """Test basic object creation in a separate domain."""
    body = {
        "name": str(uuid.uuid4()),
        "storage_class": "pulpcore.app.models.storage.FileSystem",
        "storage_settings": {"MEDIA_ROOT": "/var/lib/pulp/media/"},
    }
    domain = gen_object_with_cleanup(pulpcore_bindings.DomainsApi, body)
    domain_name = domain.name

    repo_body = {"name": str(uuid.uuid4())}
    repo = gen_object_with_cleanup(
        file_bindings.RepositoriesFileApi, repo_body, pulp_domain=domain_name
    )
    assert f"{domain_name}/api/v3/" in repo.pulp_href

    repos = file_bindings.RepositoriesFileApi.list(pulp_domain=domain_name)
    assert repos.count == 1
    assert repo.pulp_href == repos.results[0].pulp_href

    # Will list repos on default domain
    default_repos = file_bindings.RepositoriesFileApi.list(name=repo.name)
    assert default_repos.count == 0

    # Try to create an object w/ cross domain relations
    default_remote = file_remote_factory(manifest_path=basic_manifest_path, policy="immediate")
    with pytest.raises(ApiException) as e:
        repo_body = {"name": str(uuid.uuid4()), "remote": default_remote.pulp_href}
        file_bindings.RepositoriesFileApi.create(repo_body, pulp_domain=domain.name)
    assert e.value.status == 400
    # What key should this error be under? non-field-errors seems wrong
    assert json.loads(e.value.body) == {
        "non_field_errors": [f"Objects must all be apart of the {domain_name} domain."]
    }

    with pytest.raises(ApiException) as e:
        sync_body = {"remote": default_remote.pulp_href}
        file_bindings.RepositoriesFileApi.sync(repo.pulp_href, sync_body)
    assert e.value.status == 400
    assert json.loads(e.value.body) == {
        "non_field_errors": [f"Objects must all be apart of the {domain_name} domain."]
    }


@pytest.mark.parallel
def test_artifact_upload(
    pulpcore_bindings,
    gen_object_with_cleanup,
    random_artifact_factory,
    tmp_path,
    monitor_task,
):
    """Test uploading artifacts in separate domains."""
    # Should this test live in pulpcore?
    body = {
        "name": str(uuid.uuid4()),
        "storage_class": "pulpcore.app.models.storage.FileSystem",
        "storage_settings": {"MEDIA_ROOT": "/var/lib/pulp/media/"},
    }
    domain = gen_object_with_cleanup(pulpcore_bindings.DomainsApi, body)

    artifact = random_artifact_factory(pulp_domain=domain.name)

    artifacts = pulpcore_bindings.ArtifactsApi.list(pulp_domain=domain.name)
    assert artifacts.count == 1
    assert artifact.pulp_href == artifacts.results[0].pulp_href

    # Test upload api
    filename = tmp_path / str(uuid.uuid4())
    file = generate_iso(filename)  # Default size is 1024
    upload_body = {"size": file["size"]}
    upload = pulpcore_bindings.UploadsApi.create(upload_body, pulp_domain=domain.name)
    assert f"{domain.name}/api/v3/" in upload.pulp_href

    with open(filename, mode="rb") as f:
        for i, chunk_header in enumerate(("bytes 0-511/1024", "bytes 512-1023/1024")):
            cfilename = f"{filename}_chunk{i}"
            with open(cfilename, mode="wb") as cf:
                cf.write(f.read(512))
                cf.flush()
            pulpcore_bindings.UploadsApi.update(chunk_header, upload.pulp_href, cfilename)
    commit_body = {"sha256": file["digest"]}
    task = pulpcore_bindings.UploadsApi.commit(upload.pulp_href, commit_body).task
    finished = monitor_task(task)

    assert len(finished.created_resources) == 1
    second_artifact_href = finished.created_resources[0]
    assert f"{domain.name}/api/v3/" in second_artifact_href

    artifacts = pulpcore_bindings.ArtifactsApi.list(pulp_domain=domain.name)
    assert artifacts.count == 2

    second_artifact = pulpcore_bindings.ArtifactsApi.read(second_artifact_href)
    assert second_artifact.sha256 == file["digest"]

    # Test that duplicate artifact can not be uploaded in same domain
    with pytest.raises(CoreApiException) as e:
        pulpcore_bindings.ArtifactsApi.create(filename, pulp_domain=domain.name)
    assert e.value.status == 400
    assert json.loads(e.value.body) == {
        "non_field_errors": [f"Artifact with sha256 checksum of '{file['digest']}' already exists."]
    }

    # Show that duplicate artifacts can be uploaded into different domains
    dup_artifact = pulpcore_bindings.ArtifactsApi.create(filename, pulp_domain="default")
    assert "default/api/v3/" in dup_artifact.pulp_href
    assert dup_artifact.sha256 == second_artifact.sha256


@pytest.mark.parallel
def test_content_upload(
    pulpcore_bindings,
    file_bindings,
    gen_object_with_cleanup,
    tmp_path,
    monitor_task,
):
    """Test uploading of file content with domains."""
    body = {
        "name": str(uuid.uuid4()),
        "storage_class": "pulpcore.app.models.storage.FileSystem",
        "storage_settings": {"MEDIA_ROOT": "/var/lib/pulp/media/"},
    }
    domain = gen_object_with_cleanup(pulpcore_bindings.DomainsApi, body)

    filename = tmp_path / str(uuid.uuid4())
    file = generate_iso(filename)
    relative_path = "1.iso"

    task = file_bindings.ContentFilesApi.create(relative_path, file=filename).task
    task2 = file_bindings.ContentFilesApi.create(
        relative_path, file=filename, pulp_domain=domain.name
    ).task
    response = monitor_task(task)
    default_content = file_bindings.ContentFilesApi.read(response.created_resources[0])
    response = monitor_task(task2)
    domain_content = file_bindings.ContentFilesApi.read(response.created_resources[0])

    assert default_content.pulp_href != domain_content.pulp_href
    assert default_content.sha256 == domain_content.sha256 == file["digest"]
    assert default_content.relative_path == domain_content.relative_path

    domain_contents = file_bindings.ContentFilesApi.list(pulp_domain=domain.name)
    assert domain_contents.count == 1

    # Content needs to be deleted for the domain to be deleted
    body = {"orphan_protection_time": 0}
    task = pulpcore_bindings.OrphansCleanupApi.cleanup(body, pulp_domain=domain.name).task
    monitor_task(task)

    domain_contents = file_bindings.ContentFilesApi.list(pulp_domain=domain.name)
    assert domain_contents.count == 0


@pytest.mark.parallel
def test_content_promotion(
    pulpcore_bindings,
    file_bindings,
    basic_manifest_path,
    file_remote_factory,
    file_distribution_factory,
    gen_object_with_cleanup,
    monitor_task,
):
    """Tests Content promotion path with domains: Sync->Publish->Distribute"""
    body = {
        "name": str(uuid.uuid4()),
        "storage_class": "pulpcore.app.models.storage.FileSystem",
        "storage_settings": {"MEDIA_ROOT": "/var/lib/pulp/media/"},
    }
    domain = gen_object_with_cleanup(pulpcore_bindings.DomainsApi, body)

    # Sync task
    remote = file_remote_factory(
        manifest_path=basic_manifest_path, policy="immediate", pulp_domain=domain.name
    )
    repo_body = {"name": str(uuid.uuid4()), "remote": remote.pulp_href}
    repo = file_bindings.RepositoriesFileApi.create(repo_body, pulp_domain=domain.name)

    task = file_bindings.RepositoriesFileApi.sync(repo.pulp_href, {}).task
    response = monitor_task(task)
    assert len(response.created_resources) == 1

    repo = file_bindings.RepositoriesFileApi.read(repo.pulp_href)
    assert repo.latest_version_href[-2] == "1"

    # Publish task
    pub_body = {"repository": repo.pulp_href}
    task = file_bindings.PublicationsFileApi.create(pub_body, pulp_domain=domain.name).task
    response = monitor_task(task)
    assert len(response.created_resources) == 1
    pub_href = response.created_resources[0]
    pub = file_bindings.PublicationsFileApi.read(pub_href)

    assert pub.repository == repo.pulp_href

    # Distribute Task
    distro = file_distribution_factory(publication=pub.pulp_href, pulp_domain=domain.name)

    assert distro.publication == pub.pulp_href
    # Url structure should be host/CONTENT_ORIGIN/DOMAIN_PATH/BASE_PATH
    assert domain.name == distro.base_url.rstrip("/").split("/")[-2]

    # Check that content can be downloaded from base_url
    for path in ("1.iso", "2.iso", "3.iso"):
        download = download_file(f"{distro.base_url}{path}")
        assert download.response_obj.status == 200
        assert len(download.body) == 1024

    # Test that a repository version repair operation can be run without error
    response = file_bindings.RepositoriesFileVersionsApi.repair(
        repo.latest_version_href, Repair(verify_checksums=True)
    )
    results = monitor_task(response.task)
    assert results.state == "completed"
    assert results.error is None

    # Cleanup to delete the domain
    task = file_bindings.RepositoriesFileApi.delete(repo.pulp_href).task
    monitor_task(task)
    body = {"orphan_protection_time": 0}
    task = pulpcore_bindings.OrphansCleanupApi.cleanup(body, pulp_domain=domain.name).task
    monitor_task(task)


@pytest.mark.parallel
def test_domain_rbac(pulpcore_bindings, file_bindings, gen_user, gen_object_with_cleanup):
    """Test domain level-roles."""
    body = {
        "name": str(uuid.uuid4()),
        "storage_class": "pulpcore.app.models.storage.FileSystem",
        "storage_settings": {"MEDIA_ROOT": "/var/lib/pulp/media/"},
    }
    domain = gen_object_with_cleanup(pulpcore_bindings.DomainsApi, body)

    file_viewer = "file.filerepository_viewer"
    file_creator = "file.filerepository_creator"
    user_a = gen_user(username="a", domain_roles=[(file_viewer, domain.pulp_href)])
    user_b = gen_user(username="b", domain_roles=[(file_creator, domain.pulp_href)])

    # Create two repos in different domains w/ admin user
    gen_object_with_cleanup(file_bindings.RepositoriesFileApi, {"name": str(uuid.uuid4())})
    gen_object_with_cleanup(
        file_bindings.RepositoriesFileApi, {"name": str(uuid.uuid4())}, pulp_domain=domain.name
    )

    with user_b:
        repo = gen_object_with_cleanup(
            file_bindings.RepositoriesFileApi, {"name": str(uuid.uuid4())}, pulp_domain=domain.name
        )
        repos = file_bindings.RepositoriesFileApi.list(pulp_domain=domain.name)
        assert repos.count == 1
        assert repos.results[0].pulp_href == repo.pulp_href
        # Try to create a repository in default domain
        with pytest.raises(ApiException) as e:
            file_bindings.RepositoriesFileApi.create({"name": str(uuid.uuid4())})
        assert e.value.status == 403

    with user_a:
        repos = file_bindings.RepositoriesFileApi.list(pulp_domain=domain.name)
        assert repos.count == 2
        # Try to read repos in the default domain
        repos = file_bindings.RepositoriesFileApi.list()
        assert repos.count == 0
        # Try to create a repo
        with pytest.raises(ApiException) as e:
            file_bindings.RepositoriesFileApi.create(
                {"name": str(uuid.uuid4())}, pulp_domain=domain.name
            )
        assert e.value.status == 403
