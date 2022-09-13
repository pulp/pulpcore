"""Utility functions for Pulp 3 tests."""
import aiohttp
import asyncio
import uuid
import json
from collections import defaultdict
import unittest
import warnings
from urllib.parse import urljoin, urlsplit

from pulpcore.tests.suite import api, cli, config
from pulpcore.tests.suite.constants import STATUS_PATH


def execute_pulpcore_python(cli_client, command):
    """Execute command in pulpcore-manager on system under test."""
    ps_output = cli_client.run(("ps", "ax")).stdout.splitlines()
    bin_dir = "/usr/local/bin"
    for line in ps_output:
        if "pulpcore" in line and "bin/python" in line:
            bin_dir = line.split()[5].rsplit("/", maxsplit=1)[0]
    manager = "{}/pulpcore-manager".format(bin_dir)
    return cli_client.run((manager, "shell", "-c", command)).stdout.rstrip("\n")


def get_pulp_setting(cli_client, setting_name):
    """Retrieves the value of a Pulp setting from system under test."""
    command = (
        "import json; from django.conf import settings;"
        "cfg_value = getattr(settings,'{}', None);"
        "value = cfg_value if not isinstance(cfg_value, set) else list(cfg_value);"
        "print(json.dumps(value))".format(setting_name)
    )
    json_value = execute_pulpcore_python(cli_client, command)
    value = json.loads(json_value)
    return value


def require_pulp_plugins(required_plugins, exc):
    """Raise an exception if one or more plugins are missing.
    If the same exception should be pased each time this method is called,
    consider using `functools.partial`_.
    :param required_plugins: A set of plugin names, e.g. ``{'pulp-file'}``.
    :param exc: A class to instantiate and raise as an exception. Its
        constructor must accept one string argument.
    .. _functools.partial:
        https://docs.python.org/3/library/functools.html#functools.partial
    """
    missing_plugins = required_plugins - get_plugins()
    if missing_plugins:
        raise exc(
            "The following plugins are required but not installed: {}".format(missing_plugins)
        )


def get_plugins(cfg=None):
    """Return the set of plugins installed on the Pulp application.
    :param pulp_smash.config.PulpSmashConfig cfg: Information about the Pulp
        application under test.
    :returns: A set of plugin names, e.g. ``{'pulpcore', 'pulp_file'}``.
    """
    if not cfg:
        cfg = config.get_config()
    client = api.Client(cfg, api.json_handler)
    status = client.get(STATUS_PATH)
    return {version["component"] for version in status["versions"]}


def sync(cfg, remote, repo, **kwargs):
    """Sync a repository.
    :param pulp_smash.config.PulpSmashConfig cfg: Information about the Pulp host.
    :param remote: A dict of information about the remote of the repository
        to be synced.
    :param repo: A dict of information about the repository.
    :param kwargs: Keyword arguments to be merged in to the request data.
    :returns: The server's response. A dict of information about the just
        created sync.
    """
    client = api.Client(cfg)
    data = {"remote": remote["pulp_href"]}
    data.update(kwargs)
    return client.post(urljoin(repo["pulp_href"], "sync/"), data)


def modify_repo(cfg, repo, base_version=None, add_units=None, remove_units=None):
    """Modify a repository.
    :param pulp_smash.config.PulpSmashConfig cfg: Information about the Pulp host.
    :param repo: A dict of information about the repository.
    :param base_version: If provided, use a specific repository version
        instead of the latest one.
    :param add_units: A list of dicts of information about the content
        units to add.
    :param remove_units: A list of dicts of information about the content
        units to remove.
    :returns: The server's response. A dict of information about the just
        created modification operation.
    """
    client = api.Client(cfg)

    params = {}
    if add_units:
        params["add_content_units"] = [content["pulp_href"] for content in add_units]
    if remove_units:
        if remove_units == ["*"]:
            params["remove_content_units"] = remove_units
        else:
            params["remove_content_units"] = [content["pulp_href"] for content in remove_units]
    if base_version:
        params["base_version"] = base_version

    return client.post(urljoin(repo["pulp_href"], "modify/"), params)


def build_unit_url(_cfg, distribution, unit_path):
    """Build a unit url that can be used to fetch content via a distribution.
    :param pulp_smash.config.PulpSmashConfig cfg: Information about the Pulp host.
    :param distribution: A dict of information about the distribution.
    :param unit_path: A string path to the unit to be downloaded.
    """
    url_fragments = [
        _cfg.get_content_host_base_url(),
        "pulp/content",
        distribution["base_path"],
        unit_path,
    ]
    return "/".join(url_fragments)


def http_get(url, **kwargs):
    """Issue an HTTP request to the ``url`` and return the response content.
    This is useful for downloading file contents over HTTP[S].
    :param kwargs: additional kwargs to be passed to ``requests.get``.
    :returns: the response content of a GET request to ``url``.
    """

    async def send_request():
        async with aiohttp.ClientSession(raise_for_status=True) as session:
            async with session.get(url, **kwargs) as response:
                return await response.content.read()

    response = asyncio.run(send_request())
    return response


def download_content_unit(_cfg, distribution, unit_path, **kwargs):
    """Download the content unit distribution using pulp-smash config.
    :param pulp_smash.config.PulpSmashConfig cfg: Information about the Pulp host.
    :param distribution: A dict of information about the distribution.
    :param unit_path: A string path to the unit to be downloaded.
    :param kwargs: Extra arguments passed to requests.get.
    """
    unit_url = build_unit_url(_cfg, distribution, unit_path)
    return http_get(unit_url, **kwargs)


def wget_download_on_host(url, destination, cfg=None):
    """Use wget to recursively download a file or directory to the host running Pulp.
    :param url: The path the recursively download using wget.
    :param destination: Where wget should put the downloaded directory.
    :param pulp_smash.config.PulpSmashConfig cfg: Information about the Pulp host.
    """
    if not cfg:
        cfg = config.get_config()

    if cli.Client(cfg).run(("which", "wget")).returncode:
        raise unittest.SkipTest(
            "Cannot perform a download without 'wget' available on the system running Pulp."
        )

    cli.Client(cfg).run(
        (
            "wget",
            "--recursive",
            "--no-parent",
            "--no-host-directories",
            "--directory-prefix",
            destination,
            url,
        )
    )


def publish(cfg, publisher, repo, version_href=None):
    """Publish a repository.
    :param pulp_smash.config.PulpSmashConfig cfg: Information about the Pulp host.
    :param publisher: A dict of information about the publisher of the
        repository to be published.
    :param repo: A dict of information about the repository.
    :param version_href: The repository version to be published.
    :returns: A publication. A dict of information about the just created
        publication.
    """
    if version_href is None:
        body = {"repository": repo["pulp_href"]}
    else:
        body = {"repository_version": version_href}
    client = api.Client(cfg, api.json_handler)
    call_report = client.post(urljoin(publisher["pulp_href"], "publish/"), body)
    # As of this writing, Pulp 3 only returns one task. If Pulp 3 starts
    # returning multiple tasks, this may need to be re-written.
    tasks = tuple(api.poll_spawned_tasks(cfg, call_report, cfg.pulp_host.hostname))
    if len(tasks) != 1:
        message = (
            "Multiple tasks were spawned in response to API call. This is "
            "unexpected, and Pulp Smash may handle the response incorrectly. "
            "Here is the tasks generated: {}"
        )
        message = message.format(tasks)
        warnings.warn(message, RuntimeWarning)
    return client.get(tasks[-1]["created_resources"][0])


def _build_content_fetcher(content_field):
    """Build closure for fetching content from a repository.
    :param content_field: The name of a field on a RepositoryVersion, which
        contains a dict of content types and the URL at which to view content.
    :returns: A closure which returns content from the specified field.
    """

    def inner(repo, version_href=None):
        """Read the content units of a given repository.
        :param repo: A dict of information about the repository.
        :param version_href: The repository version to read. If none, read the
            latest repository version.
        :returns: A list of information about the content units present in a
            given repository version.
        """
        version_href = version_href or repo["latest_version_href"]

        if version_href is None:
            # Repository has no latest version, and therefore no content.
            return defaultdict(list)

        client = api.Client(config.get_config(), api.page_handler)
        repo_version = client.get(version_href)

        content = defaultdict(list)
        for content_type, content_dict in repo_version["content_summary"][content_field].items():
            typed_content = client.get(content_dict["href"])
            content[content_type] = typed_content
        return content

    return inner


get_content = _build_content_fetcher("present")  # pylint:disable=invalid-name
get_added_content = _build_content_fetcher("added")  # pylint:disable=invalid-name
get_removed_content = _build_content_fetcher("removed")  # pylint:disable=invalid-name


def _build_summary_fetcher(summary_field):
    """Build closure for fetching content summaries from a repository.
    :param content_field: The name of a field on a RepositoryVersion, which
        contains a dict of content types and their counts.
    :returns: A closure which returns content from the specified field.
    """

    def inner(repo, version_href=None):
        """Read the "content summary" of a given repository version.
        Repository versions have a "content_summary" which lists the content
        types and the number of units of that type present in the repo version.
        :param repo: A dict of information about the repository.
        :param version_href: The repository version to read. If none, read the
            latest repository version.
        :returns: The "content_summary" of the repo version.
        """
        version_href = version_href or repo["latest_version_href"]

        if version_href is None:
            # Repository has no latest version, and therefore no content.
            return {}

        client = api.Client(config.get_config(), api.page_handler)
        to_return = client.get(version_href)["content_summary"][summary_field]
        for key in to_return:
            # provide the old interface pre-changes from
            # https://github.com/pulp/pulpcore/pull/2
            to_return[key] = to_return[key]["count"]
        return to_return

    return inner


get_content_summary = _build_summary_fetcher("present")  # pylint:disable=invalid-name
get_added_content_summary = _build_summary_fetcher("added")  # pylint:disable=invalid-name
get_removed_content_summary = _build_summary_fetcher("removed")  # pylint:disable=invalid-name


def get_versions(repo, params=None):
    """Return repository versions, sorted by version ID.
    :param repo: A dict of information about the repository.
    :param params: Dictionary or bytes to be sent in the query string. Used to
        filter which versions are returned.
    :returns: A sorted list of dicts of information about repository versions.
    """
    client = api.Client(config.get_config(), api.page_handler)
    versions = client.get(repo["versions_href"], params=params)
    versions.sort(key=lambda version: int(urlsplit(version["pulp_href"]).path.split("/")[-2]))
    return versions


def get_artifact_paths(repo, version_href=None):
    """Return the paths of artifacts present in a given repository version.
    :param repo: A dict of information about the repository.
    :param version_href: The repository version to read.
    :returns: A set with the paths of units present in a given repository.
    """
    # content['artifact'] consists of a file path and name.
    artifact_paths = set()
    for typed_content in get_content(repo, version_href).values():
        for content in typed_content:
            # Plugins can support zero, one, or many artifacts per content unit
            if content.get("artifact"):
                artifact_paths.add(content["artifact"])
            elif content.get("artifacts"):
                for artifact in content["artifacts"]:
                    artifact_paths.add(artifact)
            else:
                continue
    return artifact_paths


def delete_version(repo, version_href=None):
    """Delete a given repository version.
    :param repo: A dict of information about the repository.
    :param version_href: The repository version that should be deleted.
    :returns: A tuple. The tasks spawned by Pulp.
    """
    version_href = version_href or repo["latest_version_href"]

    if version_href is None:
        # Repository has no latest version.
        raise ValueError("No version exists to be deleted.")

    cfg = config.get_config()
    client = api.Client(cfg, api.json_handler)
    client.delete(version_href)


def gen_distribution(**kwargs):
    """Return a semi-random dict for use in creating a Distribution."""
    data = {"base_path": str(uuid.uuid4()), "name": str(uuid.uuid4())}
    data.update(kwargs)
    return data


def gen_publisher(**kwargs):
    """Return a semi-random dict for use in creating an Publisher."""
    data = {"name": str(uuid.uuid4())}
    data.update(kwargs)
    return data


def gen_remote(url, **kwargs):
    """Return a semi-random dict for use in creating a Remote.
    :param url: The URL of an external content source.
    """
    data = {"name": str(uuid.uuid4()), "url": url}
    data.update(kwargs)
    return data


def gen_repo(**kwargs):
    """Return a semi-random dict for use in creating a Repository."""
    data = {"name": str(uuid.uuid4())}
    data.update(kwargs)
    return data


def uuid4():
    return str(uuid.uuid4())
