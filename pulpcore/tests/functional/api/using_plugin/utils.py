"""Utilities for pulpcore API tests that require the use of a plugin."""
from functools import partial
from unittest import SkipTest

from pulp_smash import api, cli, config, selectors, utils
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
    UsersApi,
    UsersRolesApi,
)
from pulpcore.client.pulp_file import DistributionsFileApi
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


def gen_pulpcore_client():
    """Return an OBJECT for pulpcore client."""
    configuration = config.get_config().get_bindings_config()
    return CoreApiClient(configuration)


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


def create_distribution(repository_href=None):
    """Utility to create a pulp_file distribution."""
    file_client = gen_file_client()
    distro_api = DistributionsFileApi(file_client)

    body = {"name": utils.uuid4(), "base_path": utils.uuid4()}
    if repository_href:
        body["repository"] = repository_href

    result = distro_api.create(body)
    distro_href = monitor_task(result.task).created_resources[0]
    distro = distro_api.read(distro_href)
    return distro


CREATE_USER_CMD = [
    "from django.contrib.auth import get_user_model",
    "from django.urls import resolve",
    "from guardian.shortcuts import assign_perm",
    "",
    "user = get_user_model().objects.create(username='{username}')",
    "user.set_password('{password}')",
    "user.save()",
    "",
    "for permission in {model_permissions!r}:",
    "    assign_perm(permission, user)",
    "",
    "for permission, obj_url in {object_permissions!r}:",
    "    func, _, kwargs = resolve(obj_url)",
    "    obj = func.cls.queryset.get(pk=kwargs['pk'])",
    "    assign_perm(permission, user, obj)",
]


DELETE_USER_CMD = [
    "from django.contrib.auth import get_user_model",
    "get_user_model().objects.get(username='{username}').delete()",
]


def gen_user(cfg=config.get_config(), model_permissions=None, object_permissions=None):
    """Create a user with a set of permissions in the pulp database."""
    cli_client = cli.Client(cfg)

    if model_permissions is None:
        model_permissions = []

    if object_permissions is None:
        object_permissions = []

    user = {
        "username": utils.uuid4(),
        "password": utils.uuid4(),
        "model_permissions": model_permissions,
        "object_permissions": object_permissions,
    }
    utils.execute_pulpcore_python(
        cli_client,
        "\n".join(CREATE_USER_CMD).format(**user),
    )

    api_config = cfg.get_bindings_config()
    api_config.username = user["username"]
    api_config.password = user["password"]
    user["core_api_client"] = CoreApiClient(api_config)
    user["api_client"] = FileApiClient(api_config)
    user["distribution_api"] = DistributionsFileApi(user["api_client"])
    return user


def del_user(user, cfg=config.get_config()):
    """Delete a user from the pulp database."""
    cli_client = cli.Client(cfg)
    utils.execute_pulpcore_python(
        cli_client,
        "\n".join(DELETE_USER_CMD).format(**user),
    )


def gen_user_rest(cfg=None, model_roles=None, object_roles=None, **kwargs):
    """Add a user with a set of roles using the REST API."""
    if cfg is None:
        cfg = config.get_config()
    api_config = cfg.get_bindings_config()
    admin_core_client = CoreApiClient(api_config)
    admin_user_api = UsersApi(admin_core_client)
    admin_user_roles_api = UsersRolesApi(admin_core_client)

    user_body = {
        "username": utils.uuid4(),
        "password": utils.uuid4(),
    }
    user_body.update(kwargs)

    user = admin_user_api.create(user_body)

    if model_roles:
        for role in model_roles:
            user_role = {"role": role, "content_object": None}
            admin_user_roles_api.create(user.pulp_href, user_role)
    if object_roles:
        for role, obj in object_roles:
            user_role = {"role": role, "content_object": obj}
            admin_user_roles_api.create(user.pulp_href, user_role)

    user_body.update(user.to_dict())
    return user_body


def del_user_rest(user_href, cfg=None):
    """Delete a user using the REST API."""
    if cfg is None:
        cfg = config.get_config()
    api_config = cfg.get_bindings_config()
    admin_core_client = CoreApiClient(api_config)
    admin_user_api = UsersApi(admin_core_client)

    admin_user_api.delete(user_href)
