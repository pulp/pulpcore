import hashlib
import pytest
import uuid
from urllib.parse import urljoin

from pulpcore.client.pulp_file import RepositorySyncURL
from pulpcore.client.pulp_file.exceptions import ApiException

from pulpcore.tests.functional.utils import (
    download_file,
    get_files_in_manifest,
)


@pytest.fixture
def generate_server_and_remote(
    gen_fixture_server, file_fixtures_root, file_remote_api_client, gen_object_with_cleanup
):
    def _generate_server_and_remote(*, manifest_path, policy):
        server = gen_fixture_server(file_fixtures_root, None)
        url = server.make_url(manifest_path)
        remote = gen_object_with_cleanup(
            file_remote_api_client,
            {"name": str(uuid.uuid4()), "url": str(url), "policy": policy},
        )
        return server, remote

    yield _generate_server_and_remote


@pytest.mark.parallel
def test_acs_validation_and_update(
    file_acs_api_client,
    file_remote_factory,
    basic_manifest_path,
    gen_object_with_cleanup,
    monitor_task,
):
    # Test that a remote with "immediate" download policy can't be used with an ACS
    immediate_remote = file_remote_factory(manifest_path=basic_manifest_path, policy="immediate")
    acs_data = {
        "name": str(uuid.uuid4()),
        "remote": immediate_remote.pulp_href,
        "paths": [],
    }
    with pytest.raises(ApiException) as exc:
        file_acs_api_client.create(acs_data)
    assert exc.value.status == 400
    assert "remote" in exc.value.body

    # Assert that paths starting with "/" are not accepted by ACS API.
    on_demand_remote = file_remote_factory(manifest_path=basic_manifest_path, policy="on_demand")
    acs_data = {
        "name": str(uuid.uuid4()),
        "remote": on_demand_remote.pulp_href,
        "paths": ["good/path", "/bad/path"],
    }
    with pytest.raises(ApiException) as exc:
        file_acs_api_client.create(acs_data)
    assert exc.value.status == 400
    assert "paths" in exc.value.body

    # Assert that an ACS can be created with valid paths
    acs_data["paths"] = ["good/path", "valid"]
    acs = gen_object_with_cleanup(file_acs_api_client, acs_data)
    assert set(acs.paths) == set(acs_data["paths"])

    # Test that an ACS's name can be updated without clobbering the paths
    new_name = str(uuid.uuid4())
    monitor_task(
        file_acs_api_client.update(acs.pulp_href, {"name": new_name, "remote": acs.remote}).task
    )
    acs = file_acs_api_client.read(acs.pulp_href)
    assert acs.name == new_name
    assert sorted(acs.paths) == sorted(acs_data["paths"])

    # Test that you can do a partial update of an ACS
    new_name = str(uuid.uuid4())
    monitor_task(file_acs_api_client.partial_update(acs.pulp_href, {"name": new_name}).task)
    acs = file_acs_api_client.read(acs.pulp_href)
    assert acs.name == new_name
    assert sorted(acs.paths) == sorted(acs_data["paths"])

    # Test that paths can be updated
    updated_paths = ["foo"]
    monitor_task(file_acs_api_client.partial_update(acs.pulp_href, {"paths": updated_paths}).task)
    acs = file_acs_api_client.read(acs.pulp_href)
    assert acs.paths == updated_paths


@pytest.mark.parallel
def test_acs_sync(
    file_repo,
    file_bindings,
    file_acs_api_client,
    basic_manifest_path,
    gen_object_with_cleanup,
    generate_server_and_remote,
    monitor_task,
    monitor_task_group,
):
    # Create the main server and remote pointing to it
    main_server, main_remote = generate_server_and_remote(
        manifest_path=basic_manifest_path, policy="immediate"
    )

    # Create an ACS server and a remote pointing to it
    acs_server, acs_remote = generate_server_and_remote(
        manifest_path=basic_manifest_path, policy="on_demand"
    )

    # Create the ACS that uses the remote from above
    acs = gen_object_with_cleanup(
        file_acs_api_client,
        {"remote": acs_remote.pulp_href, "paths": [], "name": str(uuid.uuid4())},
    )

    # Refresh ACS and assert that only the PULP_MANIFEST was downloaded
    monitor_task_group(file_acs_api_client.refresh(acs.pulp_href).task_group)
    assert len(acs_server.requests_record) == 1
    assert acs_server.requests_record[0].path == basic_manifest_path

    # Sync the repository
    repository_sync_data = RepositorySyncURL(remote=main_remote.pulp_href)
    monitor_task(
        file_bindings.RepositoriesFileApi.sync(file_repo.pulp_href, repository_sync_data).task
    )

    # Assert that only the PULP_MANIFEST was downloaded from the main remote
    assert len(main_server.requests_record) == 1
    assert main_server.requests_record[0].path == basic_manifest_path

    # Assert that the files were downloaded from the ACS remote
    expected_request_paths = {
        basic_manifest_path,
        "/basic/1.iso",
        "/basic/2.iso",
        "/basic/3.iso",
    }
    actual_requested_paths = set([request.path for request in acs_server.requests_record])
    assert len(acs_server.requests_record) == 4
    assert actual_requested_paths == expected_request_paths


@pytest.mark.parallel
def test_acs_sync_with_paths(
    file_repo,
    file_bindings,
    file_acs_api_client,
    basic_manifest_path,
    large_manifest_path,
    gen_object_with_cleanup,
    generate_server_and_remote,
    monitor_task,
    monitor_task_group,
):
    # Create the main server and remote pointing to it
    main_server, main_remote = generate_server_and_remote(
        manifest_path=basic_manifest_path, policy="immediate"
    )

    # Create an ACS server and a remote pointing to it
    acs_server, acs_remote = generate_server_and_remote(manifest_path="/", policy="on_demand")

    # Create the ACS that uses the remote from above
    acs = gen_object_with_cleanup(
        file_acs_api_client,
        {
            "remote": acs_remote.pulp_href,
            "paths": [basic_manifest_path[1:], large_manifest_path[1:]],
            "name": str(uuid.uuid4()),
        },
    )

    # Refresh ACS and assert that only the PULP_MANIFEST was downloaded
    task_group = monitor_task_group(file_acs_api_client.refresh(acs.pulp_href).task_group)
    expected_request_paths = {basic_manifest_path, large_manifest_path}
    actual_requested_paths = set([request.path for request in acs_server.requests_record])
    assert len(task_group.tasks) == 2
    assert len(acs_server.requests_record) == 2
    assert expected_request_paths == actual_requested_paths

    # Sync the repository
    repository_sync_data = RepositorySyncURL(remote=main_remote.pulp_href)
    monitor_task(
        file_bindings.RepositoriesFileApi.sync(file_repo.pulp_href, repository_sync_data).task
    )

    # Assert that only the PULP_MANIFEST was downloaded from the main remote
    assert len(main_server.requests_record) == 1
    assert main_server.requests_record[0].path == basic_manifest_path

    # Assert that the files were downloaded from the ACS remote
    expected_request_paths = {
        basic_manifest_path,
        large_manifest_path,
        "/basic/1.iso",
        "/basic/2.iso",
        "/basic/3.iso",
    }
    actual_requested_paths = set([request.path for request in acs_server.requests_record])
    assert len(acs_server.requests_record) == 5
    assert actual_requested_paths == expected_request_paths


@pytest.mark.parallel
def test_serving_acs_content(
    file_repo,
    file_bindings,
    file_acs_api_client,
    file_distribution_factory,
    basic_manifest_path,
    gen_object_with_cleanup,
    generate_server_and_remote,
    monitor_task,
    monitor_task_group,
):
    # Create the main server and remote pointing to it
    main_server, main_remote = generate_server_and_remote(
        manifest_path=basic_manifest_path, policy="on_demand"
    )

    # Create an ACS server and a remote pointing to it
    acs_server, acs_remote = generate_server_and_remote(
        manifest_path=basic_manifest_path, policy="on_demand"
    )

    # Create the ACS that uses the remote from above
    acs = gen_object_with_cleanup(
        file_acs_api_client,
        {"remote": acs_remote.pulp_href, "paths": [], "name": str(uuid.uuid4())},
    )

    # Refresh ACS
    monitor_task_group(file_acs_api_client.refresh(acs.pulp_href).task_group)

    # Create a distribution
    distribution = file_distribution_factory(repository=file_repo.pulp_href)

    # Turn on auto-publish on the repository
    monitor_task(
        file_bindings.RepositoriesFileApi.partial_update(
            file_repo.pulp_href, {"autopublish": True, "remote": main_remote.pulp_href}
        ).task
    )

    # Sync the repository
    repository_sync_data = RepositorySyncURL(remote=main_remote.pulp_href)
    monitor_task(
        file_bindings.RepositoriesFileApi.sync(file_repo.pulp_href, repository_sync_data).task
    )

    # Assert that only the PULP_MANIFEST was downloaded from the main remote
    assert len(main_server.requests_record) == 1
    assert main_server.requests_record[0].path == basic_manifest_path

    # Check what content and artifacts are in the fixture repository
    expected_files = get_files_in_manifest(main_remote.url)

    # Download one of the files and assert that it has the right checksum and that it is downloaded
    # from the ACS server.
    content_unit = list(expected_files)[0]
    content_unit_url = urljoin(distribution.base_url, content_unit[0])
    downloaded_file = download_file(content_unit_url)
    actual_checksum = hashlib.sha256(downloaded_file.body).hexdigest()
    expected_checksum = content_unit[1]
    assert expected_checksum == actual_checksum
    for request in main_server.requests_record:
        assert content_unit[0] not in request.path
    assert len(acs_server.requests_record) == 2
    assert content_unit[0] in acs_server.requests_record[1].path
