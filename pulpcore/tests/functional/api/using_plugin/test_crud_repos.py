"""Tests that CRUD repositories."""

import json
import pytest
import re

from uuid import uuid4
from aiohttp import BasicAuth
from subprocess import run
from urllib.parse import urljoin

from pulpcore.client.pulp_file.exceptions import ApiException
from pulpcore.tests.functional.utils import download_file


@pytest.mark.parallel
def test_crud_repo_full_workflow(
    file_bindings,
    file_repository_factory,
    file_remote_factory,
    basic_manifest_path,
    monitor_task,
):
    # Create repository
    repo = file_repository_factory()

    # Try to create another with the same name
    with pytest.raises(ApiException) as e:
        file_bindings.RepositoriesFileApi.create({"name": repo.name})

    assert e.value.status == 400
    error_body = json.loads(e.value.body)
    assert "name" in error_body
    assert "This field must be unique." in error_body["name"]

    # Test reading the repository
    read_repo = file_bindings.RepositoriesFileApi.read(repo.pulp_href).to_dict()
    for key, val in repo.to_dict().items():
        assert key in read_repo
        assert getattr(repo, key) == read_repo[key]

    # Read a repository by its href providing specific field list.
    config = file_bindings.RepositoriesFileApi.api_client.configuration
    auth = BasicAuth(login=config.username, password=config.password)
    full_href = urljoin(config.host, repo.pulp_href)
    for fields in [
        ("pulp_href", "pulp_created"),
        ("pulp_href", "name"),
        ("pulp_created", "versions_href", "name"),
    ]:
        response = download_file(f"{full_href}?fields={','.join(fields)}", auth=auth)
        assert sorted(fields) == sorted(json.loads(response.body).keys())

    # Read a repo by its href excluding specific fields.
    response = download_file(f"{full_href}?exclude_fields=created,name", auth=auth)
    response_fields = json.loads(response.body).keys()
    assert "created" not in response_fields
    assert "name" not in response_fields

    # Read the repository by its name.
    page = file_bindings.RepositoriesFileApi.list(name=repo.name)
    assert len(page.results) == 1
    for key, val in repo.to_dict().items():
        assert getattr(page.results[0], key) == val

    # Ensure name is displayed when listing repositories.
    for read_repo in file_bindings.RepositoriesFileApi.list().results:
        assert read_repo.name is not None

    def _do_update_attr(attr, partial=False):
        """Update a repository attribute."""
        body = {} if partial else repo.to_dict()
        function = getattr(
            file_bindings.RepositoriesFileApi, "partial_update" if partial else "update"
        )
        string = str(uuid4())
        body[attr] = string
        response = function(repo.pulp_href, body)
        monitor_task(response.task)
        # verify the update
        read_repo = file_bindings.RepositoriesFileApi.read(repo.pulp_href)
        assert string == getattr(read_repo, attr)

    # Update a repository's name using HTTP PUT.
    _do_update_attr("name")

    # Update a repository's description using HTTP PUT.
    _do_update_attr("description")

    # Update a repository's name using HTTP PATCH.
    _do_update_attr("name", partial=True)

    # Update a repository's description using HTTP PATCH.
    _do_update_attr("description", partial=True)

    # Test setting remotes on repositories.
    remote = file_remote_factory(manifest_path=basic_manifest_path, policy="on_demand")

    # verify that syncing with no remote raises an error
    with pytest.raises(ApiException):
        file_bindings.RepositoriesFileApi.sync(repo.pulp_href, {})

    # test setting the remote on the repo
    response = file_bindings.RepositoriesFileApi.partial_update(
        repo.pulp_href, {"remote": remote.pulp_href}
    )
    monitor_task(response.task)

    # test syncing without a remote
    response = file_bindings.RepositoriesFileApi.sync(repo.pulp_href, {})
    monitor_task(response.task)

    read_repo = file_bindings.RepositoriesFileApi.read(repo.pulp_href)
    repo_version = f"{repo.pulp_href}versions/1/"
    assert read_repo.latest_version_href == repo_version

    # create a publication and test that it (and repo versions) are deleted when the repo is
    # also distributions should be reset
    response = file_bindings.PublicationsFileApi.create({"repository": read_repo.pulp_href})
    publication = monitor_task(response.task).created_resources[0]

    response = file_bindings.DistributionsFileApi.create(
        {
            "name": str(uuid4()),
            "repository": read_repo.pulp_href,
            "base_path": "distribution_w_repository",
        }
    )
    distribution_w_repo = monitor_task(response.task).created_resources[0]
    assert (
        file_bindings.DistributionsFileApi.read(distribution_w_repo).repository
        == read_repo.pulp_href
    )

    response = file_bindings.DistributionsFileApi.create(
        {
            "name": str(uuid4()),
            "publication": publication,
            "base_path": "distribution_w_publication",
        }
    )
    distribution_w_publication = monitor_task(response.task).created_resources[0]
    assert (
        file_bindings.DistributionsFileApi.read(distribution_w_publication).publication
        == publication
    )

    # Delete a repository.
    response = file_bindings.RepositoriesFileApi.delete(repo.pulp_href)
    monitor_task(response.task)

    # verify the delete
    with pytest.raises(ApiException):
        file_bindings.RepositoriesFileApi.read(read_repo.pulp_href)

    with pytest.raises(ApiException):
        file_bindings.PublicationsFileApi.read(publication)

    assert file_bindings.DistributionsFileApi.read(distribution_w_repo).repository is None
    assert file_bindings.DistributionsFileApi.read(distribution_w_publication).publication is None

    # Attempt to create repository passing extraneous invalid parameter.
    # Assert response returns an error 400 including ["Unexpected field"].
    with pytest.raises(ApiException) as e:
        file_bindings.RepositoriesFileApi.create({"name": str(uuid4()), "foo": "bar"})

    assert e.value.status == 400
    error_body = json.loads(e.value.body)
    assert "foo" in error_body
    assert "Unexpected field" in error_body["foo"]


@pytest.mark.parallel
def test_crud_remotes_full_workflow(
    file_bindings,
    file_remote_factory,
    monitor_task,
    basic_manifest_path,
    file_fixture_server,
):
    remote_attrs = {
        "url": file_fixture_server.make_url(basic_manifest_path),
        "name": str(uuid4()),
        "ca_cert": None,
        "client_cert": None,
        "client_key": None,
        "tls_validation": False,
        "proxy_url": None,
        "username": "pulp",
        "password": "pulp",
        "download_concurrency": 10,
        "policy": "on_demand",
        "total_timeout": None,
        "connect_timeout": None,
        "sock_connect_timeout": None,
        "sock_read_timeout": None,
    }
    remote = file_remote_factory(**remote_attrs)

    def _compare_results(data, received):
        assert not hasattr(received, "password")

        # handle write only fields
        data.pop("username", None)
        data.pop("password", None)
        data.pop("client_key", None)

        for k in data:
            assert getattr(received, k) == data[k]

    # Compare initial-attrs vs remote created in setUp
    _compare_results(remote_attrs, remote)

    # Test updating remote
    data = {"download_concurrency": 23, "policy": "immediate"}
    response = file_bindings.RemotesFileApi.partial_update(remote.pulp_href, data)
    monitor_task(response.task)
    new_remote = file_bindings.RemotesFileApi.read(remote.pulp_href)
    _compare_results(data, new_remote)

    # Test that a password can be updated with a PUT request.
    temp_remote = file_remote_factory(
        manifest_path=basic_manifest_path, url="http://", password="new"
    )
    href = temp_remote.pulp_href
    uuid = re.search(r"/api/v3/remotes/file/file/([\w-]+)/", href).group(1)
    shell_cmd = (
        f"import pulpcore; print(pulpcore.app.models.Remote.objects.get(pk='{uuid}').password)"
    )

    # test a PUT request with a new password
    remote_update = {"name": temp_remote.name, "url": "http://", "password": "changed"}
    response = file_bindings.RemotesFileApi.update(href, remote_update)
    monitor_task(response.task)
    exc = run(["pulpcore-manager", "shell", "-c", shell_cmd], text=True, capture_output=True)
    assert exc.stdout.rstrip("\n") == "changed"

    # Test that password doesn't get unset when not passed with a PUT request.
    temp_remote = file_remote_factory(url="http://", password="new")
    href = temp_remote.pulp_href
    uuid = re.search(r"/api/v3/remotes/file/file/([\w-]+)/", href).group(1)
    shell_cmd = (
        f"import pulpcore; print(pulpcore.app.models.Remote.objects.get(pk='{uuid}').password)"
    )

    # test a PUT request without a password
    remote_update = {"name": temp_remote.name, "url": "http://"}
    response = file_bindings.RemotesFileApi.update(href, remote_update)
    monitor_task(response.task)
    exc = run(["pulpcore-manager", "shell", "-c", shell_cmd], text=True, capture_output=True)
    assert exc.stdout.rstrip("\n") == "new"

    # Test valid timeout settings (float >= 0)
    data = {
        "total_timeout": 1.0,
        "connect_timeout": 66.0,
        "sock_connect_timeout": 0.0,
        "sock_read_timeout": 3.1415926535,
    }
    response = file_bindings.RemotesFileApi.partial_update(remote.pulp_href, data)
    monitor_task(response.task)
    new_remote = file_bindings.RemotesFileApi.read(remote.pulp_href)
    _compare_results(data, new_remote)

    # Test invalid float < 0
    data = {
        "total_timeout": -1.0,
    }
    with pytest.raises(ApiException):
        file_bindings.RemotesFileApi.partial_update(remote.pulp_href, data)

    # Test invalid non-float
    data = {
        "connect_timeout": "abc",
    }
    with pytest.raises(ApiException):
        file_bindings.RemotesFileApi.partial_update(remote.pulp_href, data)

    # Test reset to empty
    data = {
        "total_timeout": False,
        "connect_timeout": None,
        "sock_connect_timeout": False,
        "sock_read_timeout": None,
    }
    response = file_bindings.RemotesFileApi.partial_update(remote.pulp_href, data)
    monitor_task(response.task)
    new_remote = file_bindings.RemotesFileApi.read(remote.pulp_href)
    _compare_results(data, new_remote)

    # Test that headers value must be a list of dicts
    data = {"headers": {"Connection": "keep-alive"}}
    with pytest.raises(ApiException):
        file_bindings.RemotesFileApi.partial_update(remote.pulp_href, data)
    data = {"headers": [1, 2, 3]}
    with pytest.raises(ApiException):
        file_bindings.RemotesFileApi.partial_update(remote.pulp_href, data)
    data = {"headers": [{"Connection": "keep-alive"}]}
    response = file_bindings.RemotesFileApi.partial_update(remote.pulp_href, data)
    monitor_task(response.task)

    # Test deleting a remote
    response = file_bindings.RemotesFileApi.delete(remote.pulp_href)
    monitor_task(response.task)
    # verify the delete
    with pytest.raises(ApiException):
        file_bindings.RemotesFileApi.read(remote.pulp_href)


@pytest.mark.parallel
def test_remote_pulp_labels(file_remote_factory, basic_manifest_path):
    """A test case for verifying whether pulp_labels are correctly assigned to a new remote."""

    pulp_labels = {"environment": "dev"}

    # Test if a created remote contains pulp_labels when passing JSON data.
    remote = file_remote_factory(
        manifest_path=basic_manifest_path, policy="on_demand", pulp_labels=pulp_labels
    )

    assert remote.pulp_labels == pulp_labels


@pytest.mark.parallel
def test_file_remote_url_validation(file_bindings, gen_object_with_cleanup):
    """A test case that verifies the validation of remotes' URLs."""

    def raise_for_invalid_request(remote_attrs):
        """Check if Pulp returns HTTP 400 after issuing an invalid request."""
        with pytest.raises(ApiException) as ae:
            file_bindings.RemotesFileApi.create(remote_attrs)
            assert ae.value.status == 400

    # Test the validation of an invalid absolute pathname.
    remote_attrs = {
        "name": str(uuid4()),
        "url": "file://tmp/good",
    }
    raise_for_invalid_request(remote_attrs)

    # Test the validation of an invalid import pathname.
    remote_attrs = {
        "name": str(uuid4()),
        "url": "file:///error/path/name",
    }
    raise_for_invalid_request(remote_attrs)

    # Test the creation of a remote after passing a valid URL.
    remote_attrs = {
        "name": str(uuid4()),
        "url": "file:///tmp/good",
    }
    gen_object_with_cleanup(file_bindings.RemotesFileApi, remote_attrs)

    # Test that the remote url can't contain username/password.
    remote_attrs = {
        "name": str(uuid4()),
        "url": "http://elladan@rivendell.org",
    }
    raise_for_invalid_request(remote_attrs)

    remote_attrs = {
        "name": str(uuid4()),
        "url": "http://elladan:pass@rivendell.org",
    }
    raise_for_invalid_request(remote_attrs)


@pytest.mark.parallel
def test_repository_remote_filter(
    file_bindings,
    file_repository_factory,
    gen_object_with_cleanup,
    file_remote_factory,
    basic_manifest_path,
):
    """Test repository's remote filter and full functionality of a HREF filter."""

    remote1 = file_remote_factory(manifest_path=basic_manifest_path, policy="on_demand")
    remote2 = file_remote_factory(manifest_path=basic_manifest_path, policy="on_demand")
    remote3 = file_remote_factory(manifest_path=basic_manifest_path, policy="on_demand")

    repo1 = file_repository_factory()
    repo2 = file_repository_factory(remote=remote1.pulp_href)
    repo3 = file_repository_factory(remote=remote2.pulp_href)
    repo4 = file_repository_factory(remote=remote2.pulp_href)
    name_in = [repo1.name, repo2.name, repo3.name, repo4.name]

    # Check that name__in filter is working
    response = file_bindings.RepositoriesFileApi.list(name__in=name_in)
    assert response.count == 4

    # Test that supplying a specific remote only returns repositories with that remote
    response = file_bindings.RepositoriesFileApi.list(remote=remote1.pulp_href)
    assert response.count == 1
    assert response.results[0].pulp_href == repo2.pulp_href

    response = file_bindings.RepositoriesFileApi.list(remote=remote2.pulp_href)
    assert response.count == 2
    assert {r.pulp_href for r in response.results} == {repo3.pulp_href, repo4.pulp_href}

    response = file_bindings.RepositoriesFileApi.list(remote=remote3.pulp_href)
    assert response.count == 0

    # Test that supplying 'null' will only show repositories without a remote
    response = file_bindings.RepositoriesFileApi.list(remote="null", name__in=name_in)
    assert response.count == 1
    assert response.results[0].pulp_href == repo1.pulp_href

    # Test that supplying a base URI of a remote will show all repositories with similar remotes
    # Using a constant here would be nice, but our URIs are dependent on the machine's settings
    BASE_URI = remote1.pulp_href[:-37]
    response = file_bindings.RepositoriesFileApi.list(remote=BASE_URI, name__in=name_in)
    assert response.count == 3
    assert {r.pulp_href for r in response.results} == {
        repo2.pulp_href,
        repo3.pulp_href,
        repo4.pulp_href,
    }
