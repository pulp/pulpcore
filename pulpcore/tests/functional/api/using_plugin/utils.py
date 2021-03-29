"""Utilities for pulpcore API tests that require the use of a plugin."""
from functools import partial
from unittest import SkipTest

from pulp_smash import api, cli, config, selectors
from pulp_smash.pulp3.bindings import monitor_task
from pulp_smash.pulp3.utils import gen_remote, gen_repo, require_pulp_3, require_pulp_plugins, sync

from pulpcore.tests.functional.api.using_plugin.constants import (
    FILE_CONTENT_PATH,
    FILE_FIXTURE_MANIFEST_URL,
    FILE_PUBLICATION_PATH,
    FILE_REMOTE_PATH,
    FILE_REPO_PATH,
)
from pulpcore.client.pulpcore import (
    ApiClient as CoreApiClient,
    ExportersPulpApi,
)
from pulpcore.client.pulp_file import ApiClient as FileApiClient

skip_if = partial(selectors.skip_if, exc=SkipTest)


def set_up_module():
    """Conditions to skip tests.

    Skip tests if not testing Pulp 3, or if either pulpcore or pulp_file
    aren't installed.
    """
    require_pulp_3(SkipTest)
    require_pulp_plugins({"core", "file"}, SkipTest)


def populate_pulp(cfg, url=None):
    """Add file contents to Pulp.

    :param pulp_smash.config.PulpSmashConfig: Information about a Pulp
        application.
    :param url: The URL to a file repository's ``PULP_MANIFEST`` file. Defaults
        to :data:`pulp_smash.constants.FILE_FIXTURE_URL` + ``PULP_MANIFEST``.
    :returns: A list of dicts, where each dict describes one file content in
        Pulp.
    """
    if url is None:
        url = FILE_FIXTURE_MANIFEST_URL

    client = api.Client(cfg, api.page_handler)
    remote = {}
    repo = {}
    try:
        remote.update(client.post(FILE_REMOTE_PATH, gen_remote(url)))
        repo.update(client.post(FILE_REPO_PATH, gen_repo()))
        sync(cfg, remote, repo)
    finally:
        if remote:
            client.delete(remote["pulp_href"])
        if repo:
            client.delete(repo["pulp_href"])
    return client.get(FILE_CONTENT_PATH)


def gen_file_client():
    """Return an OBJECT for file client."""
    configuration = config.get_config().get_bindings_config()
    return FileApiClient(configuration)


def gen_file_remote(url=FILE_FIXTURE_MANIFEST_URL, **kwargs):
    """Return a semi-random dict for use in creating a file Remote.

    :param url: The URL of an external content source.
    """
    return gen_remote(url, **kwargs)


def create_file_publication(cfg, repo, version_href=None):
    """Create a file publication.

    :param pulp_smash.config.PulpSmashConfig cfg: Information about the Pulp
        host.
    :param repo: A dict of information about the repository.
    :param version_href: A href for the repo version to be published.
    :returns: A publication. A dict of information about the just created
        publication.
    """
    if version_href:
        body = {"repository_version": version_href}
    else:
        body = {"repository": repo["pulp_href"]}
    return api.Client(cfg).post(FILE_PUBLICATION_PATH, body)


def create_repo_and_versions(syncd_repo, repo_api, versions_api, content_api):
    """Create a repo with multiple versions.

    :param syncd_repo: A Repository that has at least three Content-units for us to copy from.
    :param pulpcore.client.pulp_file.RepositoriesFileApi repo_api: client to talk to the Repository
        API
    :param pulpcore.client.pulp_file.RepositoriesFileVersionsApi versions_api: client to talk to
        the RepositoryVersions API
    :param pulpcore.client.pulp_file.ContentFilesApi content_api: client to talk to the Content API
    :returns: A (FileRepository, [FileRepositoryVersion...]) tuple
    """
    # Create a new file-repo
    a_repo = repo_api.create(gen_repo())
    # get a list of all the files from one of our existing repos
    file_list = content_api.list(repository_version=syncd_repo.latest_version_href)
    # copy files from repositories[0] into new, one file at a time
    results = file_list.results
    for a_file in results:
        href = a_file.pulp_href
        modify_response = repo_api.modify(a_repo.pulp_href, {"add_content_units": [href]})
        monitor_task(modify_response.task)
    # get all versions of that repo
    versions = versions_api.list(a_repo.pulp_href, ordering="number")
    return a_repo, versions


def delete_exporter(exporter):
    """
    Utility routine to delete an exporter and any exported files
    :param exporter : PulpExporter to delete
    """
    cfg = config.get_config()
    cli_client = cli.Client(cfg)
    core_client = CoreApiClient(configuration=cfg.get_bindings_config())
    exporter_api = ExportersPulpApi(core_client)
    cmd = ("rm", "-rf", exporter.path)

    cli_client.run(cmd, sudo=True)
    result = exporter_api.delete(exporter.pulp_href)
    monitor_task(result.task)
