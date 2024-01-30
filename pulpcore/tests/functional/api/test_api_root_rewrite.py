import pytest
import uuid
import json

from pulpcore.app import settings

"""
To run these tests:
1. Copy ../assets/api_root_rewrite.conf to /etc/nginx/pulp in your Pulp container
2. Set API_ROOT_REWRITE_HEADER to "X-API-Root"
3. Restart Pulp and nginx
"""

if settings.API_ROOT_REWRITE_HEADER != 'X-API-Root':
    pytest.skip("API_ROOT_REWRITE_HEADER not set", allow_module_level=True)


@pytest.fixture(scope="session")
def proxy_rewrite_url(bindings_cfg):
    return f"{bindings_cfg.host}/proxy/rewrite/api/v3/"


@pytest.fixture(scope="session", autouse=True)
def proxy_rewrite_set(pulpcore_bindings, proxy_rewrite_url):
    response = pulpcore_bindings.client.request("GET", proxy_rewrite_url)
    if response.status == 200:
        body = json.loads(response.data)
        for value in body.values():
            if "proxy/rewrite" not in value:
                break
        else:
            return body

    pytest.skip("Proxy rewrite path was not set up.", allow_module_level=True)


@pytest.fixture(scope="session")
def auth_headers(pulpcore_bindings):
    headers = {}
    pulpcore_bindings.client.update_params_for_auth(headers, {}, ["basicAuth"])
    return headers


@pytest.mark.parallel
def test_list_endpoints(pulpcore_bindings, proxy_rewrite_set, auth_headers):
    """Check that ALL rewritten API_ROOT endpoints are accessible."""
    API_ROOT = settings.API_ROOT.encode("utf-8")
    for endpoint, url in proxy_rewrite_set.items():
        response = pulpcore_bindings.client.request("GET", url, headers=auth_headers)
        assert response.status == 200

        if endpoint != "tasks":
            # Tasks reserved resources can have original API_ROOT
            assert API_ROOT not in response.data, f"failed on {endpoint}:{url}"


@pytest.mark.parallel
def test_full_workflow(
    file_bindings,
    basic_manifest_path,
    file_fixture_server,
    proxy_rewrite_url,
    auth_headers,
    monitor_task,
    add_to_cleanup,
):
    """Test that normal sync/publish/distribute workflow works."""
    name = str(uuid.uuid4())
    # Step 1: Create Remote
    remote_url = file_fixture_server.make_url(basic_manifest_path)
    body = {"name": name, "url": remote_url, "policy": "on_demand"}
    url = f"{proxy_rewrite_url}remotes/file/file/"
    response = file_bindings.client.request("POST", url, body=body, headers=auth_headers)
    assert response.status == 201
    remote = json.loads(response.data)
    add_to_cleanup(file_bindings.RemotesFileApi, remote["pulp_href"])
    assert remote["pulp_href"].startswith("/proxy/rewrite/")
    # Step 2: Create Repository
    body = {"name": name}
    url = f"{proxy_rewrite_url}repositories/file/file/"
    response = file_bindings.client.request("POST", url, body=body, headers=auth_headers)
    assert response.status == 201
    repository = json.loads(response.data)
    add_to_cleanup(file_bindings.RepositoriesFileApi, repository["pulp_href"])
    assert repository["pulp_href"].startswith("/proxy/rewrite/")
    assert repository["versions_href"].startswith("/proxy/rewrite/")
    assert repository["latest_version_href"].startswith("/proxy/rewrite/")
    # Step 3: Sync Repository w/ Remote
    body = {"remote": remote["pulp_href"]}
    url = f"{file_bindings.client.configuration.host}{repository['pulp_href']}sync/"
    response = file_bindings.client.request("POST", url, body=body, headers=auth_headers)
    assert response.status == 202
    task_response = json.loads(response.data)
    assert task_response["task"].startswith("/proxy/rewrite/")
    task = monitor_task(task_response["task"])
    assert len(task.created_resources) == 1
    repo_ver = task.created_resources[0]
    assert repo_ver.startswith("/proxy/rewrite/")
    repo_ver = file_bindings.RepositoriesFileVersionsApi.read(repo_ver)
    assert repo_ver.pulp_href.startswith("/proxy/rewrite/")
    added_href = repo_ver.content_summary.added["file.file"]["href"]
    assert added_href.count("/proxy/rewrite/") == 2  # start of href & one for repo-ver query param
    # Step 4: Publish Repository
    body = {"repository_version": repo_ver.pulp_href}
    url = f"{proxy_rewrite_url}publications/file/file/"
    response = file_bindings.client.request("POST", url, body=body, headers=auth_headers)
    assert response.status == 202
    task = monitor_task(json.loads(response.data)["task"])
    assert len(task.created_resources) == 1
    publication = task.created_resources[0]
    add_to_cleanup(file_bindings.PublicationsFileApi, publication)
    assert publication.startswith("/proxy/rewrite/")
    publication = file_bindings.PublicationsFileApi.read(publication)
    assert publication.pulp_href.startswith("/proxy/rewrite/")
    assert publication.repository == repository["pulp_href"]
    assert publication.repository_version == repo_ver.pulp_href
    # Step 5: Distribute Publication
    body = {"name": name, "base_path": name, "publication": publication.pulp_href}
    url = f"{proxy_rewrite_url}distributions/file/file/"
    response = file_bindings.client.request("POST", url, body=body, headers=auth_headers)
    assert response.status == 202
    task = monitor_task(json.loads(response.data)["task"])
    assert len(task.created_resources) == 1
    distribution = task.created_resources[0]
    add_to_cleanup(file_bindings.DistributionsFileApi, distribution)
    assert distribution.startswith("/proxy/rewrite/")
    distribution = file_bindings.DistributionsFileApi.read(distribution)
    assert distribution.pulp_href.startswith("/proxy/rewrite")
    assert distribution.publication == publication.pulp_href
