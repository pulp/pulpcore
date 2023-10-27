import datetime
import multiprocessing
import tempfile
import requests

from collections import namedtuple
from urllib.parse import urljoin
from uuid import uuid4

from .pulpperf import utils
from .pulpperf import reporting

Args = namedtuple("Arguments", "limit processes repositories")


def test_performance(
    gen_object_with_cleanup,
    file_repository_api_client,
    file_repository_factory,
    file_remote_api_client,
    file_publication_api_client,
    file_distribution_api_client,
    fixtures_cfg,
    monitor_task,
    bindings_cfg,
):
    """Test performance of the plugin."""
    fixture_url = urljoin(fixtures_cfg.remote_fixtures_origin, "file-perf/")
    args = Args(limit=100, processes=1, repositories=[fixture_url])
    data = []

    auth = (bindings_cfg.username, bindings_cfg.password)

    """Measure time of synchronization."""

    for r in args.repositories:
        data.append({"remote_url": r})

    for r in data:
        if r["remote_url"] not in args.repositories:
            continue
        r["repository_name"] = str(uuid4())
        r["repository_href"] = file_repository_api_client.create(
            {"name": r["repository_name"]}
        ).pulp_href
        r["remote_name"] = str(uuid4())
        r["remote_href"] = gen_object_with_cleanup(
            file_remote_api_client,
            {"name": r["remote_name"], "url": r["remote_url"] + "PULP_MANIFEST"},
        ).pulp_href

    responses = []
    for r in data:
        if r["remote_url"] not in args.repositories:
            continue
        body = {"remote": r["remote_href"], "mirror": False}
        response = file_repository_api_client.sync(r["repository_href"], body)
        responses.append(response)

    results = [monitor_task(response.task) for response in responses]
    reporting.report_tasks_stats("Sync tasks", results)

    """Measure time of resynchronization."""
    responses = []
    for r in data:
        body = {"remote": r["remote_href"], "mirror": False}
        response = file_repository_api_client.sync(r["repository_href"], body)
        responses.append(response)

    results = [monitor_task(response.task) for response in responses]
    reporting.report_tasks_stats("Resync tasks", results)

    """Measure time of repository publishing."""
    responses = []
    for r in data:
        response = file_publication_api_client.create({"repository": r["repository_href"]})
        responses.append(response)

    results = [monitor_task(response.task) for response in responses]
    reporting.report_tasks_stats("Publication tasks", results)

    for i in range(len(results)):
        data[i]["publication_href"] = results[i].created_resources[0]
        data[i]["repository_version_href"] = file_publication_api_client.read(
            data[i]["publication_href"]
        ).repository_version

    responses = []
    for r in data:
        r["distribution_name"] = str(uuid4())
        r["distribution_base_path"] = str(uuid4())
        body = {
            "name": r["distribution_name"],
            "base_path": r["distribution_base_path"],
            "publication": r["publication_href"],
        }
        response = file_distribution_api_client.create(body)
        responses.append(response)

    results = [monitor_task(response.task) for response in responses]
    reporting.report_tasks_stats("Distribution tasks", results)

    for i in range(len(results)):
        data[i]["distribution_href"] = results[i].created_resources[0]
        data[i]["download_base_url"] = file_distribution_api_client.read(
            data[i]["distribution_href"]
        ).base_url

    """Measure time of repository downloading."""
    before = datetime.datetime.utcnow()

    for r in data:
        params = []
        pulp_manifest = utils.parse_pulp_manifest(r["remote_url"] + "PULP_MANIFEST")
        for f, _, s in pulp_manifest[: args.limit]:
            params.append((r["download_base_url"], f, s))
        with multiprocessing.Pool(processes=args.processes) as pool:
            pool.starmap(download, params)

    after = datetime.datetime.utcnow()
    reporting.print_fmt_experiment_time("Repository download", before, after)

    """Measure time of inspecting the repository content."""
    before = datetime.datetime.utcnow()

    durations_list = []
    content_url = bindings_cfg.host + "/pulp/api/v3/content/file/files/"
    for r in data:
        duration, content = utils.measureit(
            list_units_in_repo_ver, content_url, r["repository_version_href"], auth
        )
        durations_list.append(duration)

        params = []
        for c in content[: args.limit]:
            url = c.get("pulp_href")
            params.append((get, bindings_cfg.host + url, None, auth))
        with multiprocessing.Pool(processes=args.processes) as pool:
            pool.starmap(utils.measureit, params)
    after = datetime.datetime.utcnow()
    reporting.print_fmt_experiment_time("Content inspection", before, after)

    """Measure time of repository cloning."""
    for r in data:
        r["repository_clone1_name"] = str(uuid4())
        r["repository_clone1_href"] = file_repository_factory(
            name=r["repository_clone1_name"]
        ).pulp_href
        r["repository_clone2_name"] = str(uuid4())
        r["repository_clone2_href"] = file_repository_factory(
            name=r["repository_clone2_name"]
        ).pulp_href

    responses = []
    for r in data:
        body = {"base_version": r["repository_version_href"]}
        response = file_repository_api_client.modify(r["repository_clone1_href"], body)
        responses.append(response)

    results = [monitor_task(response.task) for response in responses]
    reporting.report_tasks_stats("Version clone with base_version tasks", results)

    hrefs = [
        i["pulp_href"]
        for i in list_units_in_repo_ver(content_url, r["repository_version_href"], auth)
    ]

    responses = []
    for r in data:
        body = {"add_content_units": hrefs}
        response = file_repository_api_client.modify(r["repository_clone2_href"], body)
        responses.append(response)

    results = [monitor_task(response.task) for response in responses]
    reporting.report_tasks_stats("Version clone with add_content_units tasks", results)


def download(base_url, file_name, file_size):
    """Download file with expected size and drop it."""
    with tempfile.TemporaryFile() as downloaded_file:
        full_url = urljoin(base_url, file_name)
        duration, response = utils.measureit(requests.get, full_url)
        response.raise_for_status()
        downloaded_file.write(response.content)
        assert downloaded_file.tell() == file_size
        return duration


def get(url, params=None, auth=None):
    return requests.get(url, params=params, auth=auth)


def get_results(url, params=None, auth=None):
    """Wrapper around requests.get with some simplification in our case."""
    out = []
    params["limit"] = 100
    params["offset"] = 0
    while True:
        data = get(url, params=params, auth=auth).json()
        out += data["results"]
        params["offset"] += 100
        if data["next"] is None:
            break
    return out


def list_units_in_repo_ver(content_url, repo_ver, auth=None):
    """List the file content with all the fields"""
    return get_results(content_url, params={"repository_version": repo_ver}, auth=auth)
