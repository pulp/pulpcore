import os
import uuid

import pytest

from pulpcore.tests.functional.utils import BindingsNamespace, generate_iso, generate_manifest

# Api Bindings fixtures


@pytest.fixture(scope="session")
def file_bindings(_api_client_set, bindings_cfg):
    """
    A namespace providing preconfigured pulp_file api clients.

    e.g. `file_bindings.RepositoriesFileApi.list()`.
    """
    from pulpcore.client import pulp_file as file_bindings_module

    api_client = file_bindings_module.ApiClient(bindings_cfg)
    _api_client_set.add(api_client)
    yield BindingsNamespace(file_bindings_module, api_client)
    _api_client_set.remove(api_client)


# Factory fixtures


@pytest.fixture
def file_random_content_unit(file_content_unit_with_name_factory):
    return file_content_unit_with_name_factory(str(uuid.uuid4()))


@pytest.fixture
def file_content_unit_with_name_factory(file_bindings, random_artifact_factory, monitor_task):
    def _file_content_unit_with_name_factory(name):
        artifact_attrs = {"artifact": random_artifact_factory().pulp_href, "relative_path": name}
        return file_bindings.ContentFilesApi.read(
            monitor_task(
                file_bindings.ContentFilesApi.create(**artifact_attrs).task
            ).created_resources[0]
        )

    return _file_content_unit_with_name_factory


@pytest.fixture
def file_repo(file_bindings, gen_object_with_cleanup):
    body = {"name": str(uuid.uuid4())}
    return gen_object_with_cleanup(file_bindings.RepositoriesFileApi, body)


@pytest.fixture
def file_repo_with_auto_publish(file_bindings, gen_object_with_cleanup):
    body = {"name": str(uuid.uuid4()), "autopublish": True}
    return gen_object_with_cleanup(file_bindings.RepositoriesFileApi, body)


@pytest.fixture(scope="class")
def file_distribution_factory(file_bindings, gen_object_with_cleanup):
    def _file_distribution_factory(pulp_domain=None, **body):
        data = {"base_path": str(uuid.uuid4()), "name": str(uuid.uuid4())}
        data.update(body)
        kwargs = {}
        if pulp_domain:
            kwargs["pulp_domain"] = pulp_domain
        return gen_object_with_cleanup(file_bindings.DistributionsFileApi, data, **kwargs)

    return _file_distribution_factory


@pytest.fixture(scope="class")
def file_fixtures_root(tmp_path_factory):
    fixture_dir = tmp_path_factory.mktemp("fixtures")
    return fixture_dir


@pytest.fixture(scope="class")
def write_3_iso_file_fixture_data_factory(file_fixtures_root):
    def _write_3_iso_file_fixture_data_factory(name, overwrite=False, seed=None):
        file_fixtures_root.joinpath(name).mkdir(exist_ok=overwrite)
        file1 = generate_iso(file_fixtures_root.joinpath(f"{name}/1.iso"), seed=seed)
        file2 = generate_iso(file_fixtures_root.joinpath(f"{name}/2.iso"), seed=seed)
        file3 = generate_iso(file_fixtures_root.joinpath(f"{name}/3.iso"), seed=seed)
        generate_manifest(
            file_fixtures_root.joinpath(f"{name}/PULP_MANIFEST"), [file1, file2, file3]
        )
        return f"/{name}/PULP_MANIFEST"

    return _write_3_iso_file_fixture_data_factory


@pytest.fixture(scope="class")
def basic_manifest_path(write_3_iso_file_fixture_data_factory):
    return write_3_iso_file_fixture_data_factory("basic")


@pytest.fixture(scope="class")
def copy_manifest_only_factory(file_fixtures_root):
    def _copy_manifest_only(name):
        file_fixtures_root.joinpath(f"{name}-manifest").mkdir()
        # TODO this file isn't even guaranteed to be there. What's going on here?
        src = file_fixtures_root.joinpath(f"{name}/PULP_MANIFEST")
        dst = file_fixtures_root.joinpath(f"{name}-manifest/PULP_MANIFEST")
        os.symlink(src, dst)
        return f"/{name}-manifest/PULP_MANIFEST"

    return _copy_manifest_only


@pytest.fixture(scope="class")
def basic_manifest_only_path(copy_manifest_only_factory):
    return copy_manifest_only_factory("basic")


@pytest.fixture(scope="class")
def large_manifest_path(file_fixtures_root):
    one_megabyte = 1048576
    file_fixtures_root.joinpath("large").mkdir()
    file1 = generate_iso(file_fixtures_root.joinpath("large/1.iso"), 10 * one_megabyte)
    generate_manifest(file_fixtures_root.joinpath("large/PULP_MANIFEST"), [file1])
    return "/large/PULP_MANIFEST"


@pytest.fixture(scope="class")
def range_header_manifest_path(file_fixtures_root):
    """A path to a File repository manifest that contains 8 unique files each 4mb in size."""
    one_megabyte = 1048576
    file_fixtures_root.joinpath("range/foo").mkdir(parents=True)
    files = [
        generate_iso(
            file_fixtures_root.joinpath(f"range/foo/{i}.iso"), 4 * one_megabyte, f"foo/{i}.iso"
        )
        for i in range(8)
    ]

    generate_manifest(
        file_fixtures_root.joinpath("range/PULP_MANIFEST"),
        files,
    )
    return "/range/PULP_MANIFEST"


@pytest.fixture(scope="class")
def manifest_path_with_commas(file_fixtures_root):
    file_fixtures_root.joinpath("comma_test").mkdir()
    file_fixtures_root.joinpath("comma_test/comma,folder").mkdir()
    file_fixtures_root.joinpath("comma_test/basic_folder").mkdir()
    file1 = generate_iso(file_fixtures_root.joinpath("comma_test/comma,folder/,comma,,file,.iso"))
    file2 = generate_iso(file_fixtures_root.joinpath("comma_test/comma,folder/basic_file.iso"))
    file3 = generate_iso(file_fixtures_root.joinpath("comma_test/basic_folder/comma,file.iso"))
    generate_manifest(
        file_fixtures_root.joinpath("comma_test/PULP_MANIFEST"), [file1, file2, file3]
    )
    return "/comma_test/PULP_MANIFEST"


@pytest.fixture(scope="class")
def invalid_manifest_path(file_fixtures_root, basic_manifest_path):
    file_path_to_corrupt = file_fixtures_root / "basic/1.iso"
    with open(file_path_to_corrupt, "w") as f:
        f.write("this is not the right data")
    return basic_manifest_path


@pytest.fixture(scope="class")
def duplicate_filename_paths(write_3_iso_file_fixture_data_factory):
    return (
        write_3_iso_file_fixture_data_factory("file"),
        write_3_iso_file_fixture_data_factory("file2"),
    )


@pytest.fixture(scope="class")
def missing_file_path(file_fixtures_root):
    file_fixtures_root.joinpath("missing_file").mkdir()
    file = {"name": "missing_file/1.iso", "digest": "1234567890", "size": 100}
    generate_manifest(file_fixtures_root.joinpath("missing_file/PULP_MANIFEST"), [file])
    return "/missing_file/PULP_MANIFEST"


@pytest.fixture(scope="class")
def file_fixture_server_ssl_client_cert_req(
    ssl_ctx_req_client_auth, file_fixtures_root, gen_fixture_server
):
    return gen_fixture_server(file_fixtures_root, ssl_ctx_req_client_auth)


@pytest.fixture(scope="class")
def file_fixture_server_ssl(ssl_ctx, file_fixtures_root, gen_fixture_server):
    return gen_fixture_server(file_fixtures_root, ssl_ctx)


@pytest.fixture(scope="class")
def file_fixture_server(file_fixtures_root, gen_fixture_server):
    return gen_fixture_server(file_fixtures_root, None)


@pytest.fixture(scope="class")
def file_remote_factory(file_fixture_server, file_bindings, gen_object_with_cleanup):
    def _file_remote_factory(
        manifest_path=None, url=None, policy="immediate", pulp_domain=None, **body
    ):
        if not url:
            assert manifest_path is not None
            url = file_fixture_server.make_url(manifest_path)

        name = body.get("name") or str(uuid.uuid4())
        body.update({"url": str(url), "policy": policy, "name": name})
        kwargs = {}
        if pulp_domain:
            kwargs["pulp_domain"] = pulp_domain
        return gen_object_with_cleanup(file_bindings.RemotesFileApi, body, **kwargs)

    return _file_remote_factory


@pytest.fixture(scope="class")
def file_remote_ssl_factory(
    file_fixture_server_ssl,
    file_bindings,
    tls_certificate_authority_cert,
    gen_object_with_cleanup,
):
    def _file_remote_ssl_factory(*, manifest_path, policy, **kwargs):
        url = file_fixture_server_ssl.make_url(manifest_path)
        kwargs.update(
            {
                "url": str(url),
                "policy": policy,
                "name": str(uuid.uuid4()),
                "ca_cert": tls_certificate_authority_cert,
            }
        )
        return gen_object_with_cleanup(file_bindings.RemotesFileApi, kwargs)

    return _file_remote_ssl_factory


@pytest.fixture(scope="class")
def file_remote_client_cert_req_factory(
    file_fixture_server_ssl_client_cert_req,
    file_bindings,
    tls_certificate_authority_cert,
    client_tls_certificate_cert_pem,
    client_tls_certificate_key_pem,
    gen_object_with_cleanup,
):
    def _file_remote_client_cert_req_factory(*, manifest_path, policy, **kwargs):
        url = file_fixture_server_ssl_client_cert_req.make_url(manifest_path)
        kwargs.update(
            {
                "url": str(url),
                "policy": policy,
                "name": str(uuid.uuid4()),
                "ca_cert": tls_certificate_authority_cert,
                "client_cert": client_tls_certificate_cert_pem,
                "client_key": client_tls_certificate_key_pem,
            }
        )
        return gen_object_with_cleanup(file_bindings.RemotesFileApi, kwargs)

    return _file_remote_client_cert_req_factory


@pytest.fixture(scope="class")
def file_repository_factory(file_bindings, gen_object_with_cleanup):
    """A factory to generate a File Repository with auto-deletion after the test run."""

    def _file_repository_factory(pulp_domain=None, **body):
        kwargs = {}
        if pulp_domain:
            kwargs["pulp_domain"] = pulp_domain
        body.setdefault("name", str(uuid.uuid4()))
        return gen_object_with_cleanup(file_bindings.RepositoriesFileApi, body, **kwargs)

    return _file_repository_factory


@pytest.fixture(scope="class")
def file_publication_factory(file_bindings, gen_object_with_cleanup):
    """A factory to generate a File Publication with auto-deletion after the test run."""

    def _file_publication_factory(**kwargs):
        extra_args = {}
        if pulp_domain := kwargs.pop("pulp_domain", None):
            extra_args["pulp_domain"] = pulp_domain
        # XOR check on repository and repository_version
        assert bool("repository" in kwargs) ^ bool("repository_version" in kwargs)
        return gen_object_with_cleanup(file_bindings.PublicationsFileApi, kwargs, **extra_args)

    return _file_publication_factory


@pytest.fixture(scope="class")
def generate_server_and_remote(
    file_bindings, gen_fixture_server, file_fixtures_root, gen_object_with_cleanup
):
    def _generate_server_and_remote(*, manifest_path, policy):
        server = gen_fixture_server(file_fixtures_root, None)
        url = server.make_url(manifest_path)
        remote = gen_object_with_cleanup(
            file_bindings.RemotesFileApi,
            {"name": str(uuid.uuid4()), "url": str(url), "policy": policy},
        )
        return server, remote

    yield _generate_server_and_remote


# Git remote fixtures


@pytest.fixture
def file_git_remote_factory(file_bindings, gen_object_with_cleanup):
    def _file_git_remote_factory(url, git_ref="HEAD", **kwargs):
        body = {"name": str(uuid.uuid4()), "url": url, "git_ref": git_ref}
        body.update(kwargs)
        return gen_object_with_cleanup(file_bindings.RemotesGitApi, body)

    return _file_git_remote_factory
