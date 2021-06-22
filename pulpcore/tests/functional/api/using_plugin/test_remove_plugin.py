import pytest

from pulp_smash.pulp3.utils import gen_repo


@pytest.mark.nightly
def test_remove_plugin(
    cli_client,
    delete_orphans_pre,
    file_fixture_gen_file_repo,
    file_repo_api_client,
    start_and_check_services,
    stop_and_check_services,
):
    repo_name = "repo for plugin removal test"
    file_repo_pre_removal = file_repo_api_client.create(gen_repo(name=repo_name))

    assert stop_and_check_services() is True

    res = cli_client.run(["pulpcore-manager", "remove-plugin", "file"])
    assert "Successfully removed" in res.stdout

    # Without uninstalling the package just run migrations again to mimic the reinstallation
    # of a plugin at least from pulp's perspective
    res = cli_client.run(["pulpcore-manager", "migrate", "file"])
    assert res.stdout.endswith("updated.\n") is True

    assert start_and_check_services() is True

    # create a repo with the same name as before the removal
    file_repo_post_reinstall = file_fixture_gen_file_repo(name=repo_name)

    assert file_repo_pre_removal.name == file_repo_post_reinstall.name
    assert file_repo_pre_removal.pulp_href != file_repo_post_reinstall.pulp_href
