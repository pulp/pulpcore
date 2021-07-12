"""Tests that CRUD repositories."""
import json
import re
import time
import unittest
from itertools import permutations
from urllib.parse import urljoin

from pulp_smash import api, cli, config, utils
from pulp_smash.pulp3.bindings import monitor_task
from pulp_smash.pulp3.utils import gen_repo

from requests.exceptions import HTTPError

from pulpcore.tests.functional.api.using_plugin.utils import gen_file_remote
from pulpcore.tests.functional.api.using_plugin.constants import (
    FILE_FIXTURE_MANIFEST_URL,
    FILE_REMOTE_PATH,
    FILE_REPO_PATH,
)
from pulpcore.tests.functional.utils import set_up_module as setUpModule  # noqa:F401
from pulpcore.tests.functional.utils import skip_if

from pulpcore.client.pulp_file.exceptions import ApiException
from pulpcore.client.pulp_file import (
    ApiClient as FileApiClient,
    FileFileRemote,
    RemotesFileApi,
)


class CRUDRepoTestCase(unittest.TestCase):
    """CRUD repositories."""

    @classmethod
    def setUpClass(cls):
        """Create class-wide variables."""
        cls.cfg = config.get_config()
        cls.repo = {}

    def setUp(self):
        """Create an API client."""
        self.client = api.Client(self.cfg, api.json_handler)

    def test_01_create_repo(self):
        """Create repository."""
        type(self).repo = self.client.post(FILE_REPO_PATH, gen_repo())

    @skip_if(bool, "repo", False)
    def test_02_create_same_name(self):
        """Try to create a second repository with an identical name.

        * `Pulp Smash #882 <https://github.com/pulp/pulp-smash/issues/882>`_.
        * `Pulp Smash #1055
        <https://github.com/pulp/pulp-smash/issues/1055>`_.
        """
        self.client.response_handler = api.echo_handler
        response = self.client.post(FILE_REPO_PATH, gen_repo(name=self.repo["name"]))
        self.assertIn("unique", response.json()["name"][0])
        self.assertEqual(response.status_code, 400)

    @skip_if(bool, "repo", False)
    def test_02_read_repo(self):
        """Read a repository by its href."""
        repo = self.client.get(self.repo["pulp_href"])
        for key, val in self.repo.items():
            with self.subTest(key=key):
                self.assertEqual(repo[key], val)

    @skip_if(bool, "repo", False)
    def test_02_read_repo_with_specific_fields(self):
        """Read a repository by its href providing specific field list.

        Permutate field list to ensure different combinations on result.
        """
        fields = (
            "pulp_href",
            "pulp_created",
            "versions_href",
            "latest_version_href",
            "name",
            "description",
        )
        for field_pair in permutations(fields, 2):
            # ex: field_pair = ('pulp_href', 'created')
            with self.subTest(field_pair=field_pair):
                repo = self.client.get(
                    self.repo["pulp_href"], params={"fields": ",".join(field_pair)}
                )
                self.assertEqual(sorted(field_pair), sorted(repo.keys()))

    @skip_if(bool, "repo", False)
    def test_02_read_repo_without_specific_fields(self):
        """Read a repo by its href excluding specific fields."""
        # requests doesn't allow the use of != in parameters.
        url = "{}?exclude_fields=created,name".format(self.repo["pulp_href"])
        repo = self.client.get(url)
        response_fields = repo.keys()
        self.assertNotIn("created", response_fields)
        self.assertNotIn("name", response_fields)

    @skip_if(bool, "repo", False)
    def test_02_read_repos(self):
        """Read the repository by its name."""
        page = self.client.get(FILE_REPO_PATH, params={"name": self.repo["name"]})
        self.assertEqual(len(page["results"]), 1)
        for key, val in self.repo.items():
            with self.subTest(key=key):
                self.assertEqual(page["results"][0][key], val)

    @skip_if(bool, "repo", False)
    def test_02_read_all_repos(self):
        """Ensure name is displayed when listing repositories.

        See Pulp #2824 <https://pulp.plan.io/issues/2824>`_
        """
        for repo in self.client.get(FILE_REPO_PATH)["results"]:
            self.assertIsNotNone(repo["name"])

    @skip_if(bool, "repo", False)
    def test_03_fully_update_name(self):
        """Update a repository's name using HTTP PUT.

        See: `Pulp #3101 <https://pulp.plan.io/issues/3101>`_
        """
        self.do_fully_update_attr("name")

    @skip_if(bool, "repo", False)
    def test_03_fully_update_desc(self):
        """Update a repository's description using HTTP PUT."""
        self.do_fully_update_attr("description")

    def do_fully_update_attr(self, attr):
        """Update a repository attribute using HTTP PUT.

        :param attr: The name of the attribute to update. For example,
            "description." The attribute to update must be a string.
        """
        repo = self.client.get(self.repo["pulp_href"])
        string = utils.uuid4()
        repo[attr] = string
        self.client.put(repo["pulp_href"], repo)

        # verify the update
        repo = self.client.get(repo["pulp_href"])
        self.assertEqual(string, repo[attr])

    @skip_if(bool, "repo", False)
    def test_03_partially_update_name(self):
        """Update a repository's name using HTTP PATCH.

        See: `Pulp #3101 <https://pulp.plan.io/issues/3101>`_
        """
        self.do_partially_update_attr("name")

    @skip_if(bool, "repo", False)
    def test_03_partially_update_desc(self):
        """Update a repository's description using HTTP PATCH."""
        self.do_partially_update_attr("description")

    def do_partially_update_attr(self, attr):
        """Update a repository attribute using HTTP PATCH.

        :param attr: The name of the attribute to update. For example,
            "description." The attribute to update must be a string.
        """
        string = utils.uuid4()
        self.client.patch(self.repo["pulp_href"], {attr: string})

        # verify the update
        repo = self.client.get(self.repo["pulp_href"])
        self.assertEqual(repo[attr], string)

    @skip_if(bool, "repo", False)
    def test_03_set_remote_on_repository(self):
        """Test setting remotes on repositories."""
        body = gen_file_remote()
        remote = self.client.post(FILE_REMOTE_PATH, body)

        # verify that syncing with no remote raises an error
        with self.assertRaises(HTTPError):
            self.client.post(urljoin(self.repo["pulp_href"], "sync/"))

        # test setting the remote on the repo
        self.client.patch(self.repo["pulp_href"], {"remote": remote["pulp_href"]})

        # test syncing without a remote
        self.client.post(urljoin(self.repo["pulp_href"], "sync/"))

        repo = self.client.get(self.repo["pulp_href"])
        self.assertEqual(repo["latest_version_href"], f"{repo['pulp_href']}versions/1/")

    @skip_if(bool, "repo", False)
    def test_04_delete_repo(self):
        """Delete a repository."""
        self.client.delete(self.repo["pulp_href"])

        # verify the delete
        with self.assertRaises(HTTPError):
            self.client.get(self.repo["pulp_href"])

    def test_negative_create_repo_with_invalid_parameter(self):
        """Attempt to create repository passing extraneous invalid parameter.

        Assert response returns an error 400 including ["Unexpected field"].
        """
        response = api.Client(self.cfg, api.echo_handler).post(FILE_REPO_PATH, gen_repo(foo="bar"))
        assert response.status_code == 400
        assert response.json()["foo"] == ["Unexpected field"]


class CRUDRemoteTestCase(unittest.TestCase):
    """CRUD remotes."""

    @classmethod
    def setUpClass(cls):
        """Create class-wide variables."""
        cls.cfg = config.get_config()

    def setUp(self):
        self.client = FileApiClient(self.cfg.get_bindings_config())
        self.remotes_api = RemotesFileApi(self.client)
        self.remote_attrs = {
            "name": utils.uuid4(),
            "url": FILE_FIXTURE_MANIFEST_URL,
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
        self.remote = self.remotes_api.create(self.remote_attrs)

    def _compare_results(self, data, received):
        self.assertFalse(hasattr(received, "password"))

        # handle write only fields
        data.pop("username", None)
        data.pop("password", None)
        data.pop("client_key", None)

        for k in data:
            self.assertEqual(getattr(received, k), data[k])

    def test_read(self):
        # Compare initial-attrs vs remote created in setUp
        self._compare_results(self.remote_attrs, self.remote)

    def test_update(self):
        data = {"download_concurrency": 23, "policy": "immediate"}
        self.remotes_api.partial_update(self.remote.pulp_href, data)
        time.sleep(1)  # without this, the read returns the pre-patch values
        new_remote = self.remotes_api.read(self.remote.pulp_href)
        self._compare_results(data, new_remote)

    def test_password_writeable(self):
        """Test that a password can be updated with a PUT request."""
        cli_client = cli.Client(self.cfg)
        remote = self.remotes_api.create({"name": "test_pass", "url": "http://", "password": "new"})
        href = remote.pulp_href
        uuid = re.search(r"/pulp/api/v3/remotes/file/file/([\w-]+)/", href).group(1)
        shell_cmd = (
            f"import pulpcore; print(pulpcore.app.models.Remote.objects.get(pk='{uuid}').password)"
        )

        self.addCleanup(self.remotes_api.delete, href)

        # test a PUT request with a new password
        remote_update = FileFileRemote(name="test_pass", url="http://", password="changed")
        response = self.remotes_api.update(href, remote_update)
        monitor_task(response.task)
        exc = cli_client.run(["pulpcore-manager", "shell", "-c", shell_cmd])
        self.assertEqual(exc.stdout.rstrip("\n"), "changed")

    def test_password_not_unset(self):
        """Test that password doesn't get unset when not passed with a PUT request."""
        cli_client = cli.Client(self.cfg)
        remote = self.remotes_api.create({"name": "test_pass", "url": "http://", "password": "new"})
        href = remote.pulp_href
        uuid = re.search(r"/pulp/api/v3/remotes/file/file/([\w-]+)/", href).group(1)
        shell_cmd = (
            f"import pulpcore; print(pulpcore.app.models.Remote.objects.get(pk='{uuid}').password)"
        )

        self.addCleanup(self.remotes_api.delete, href)

        # test a PUT request without a password
        remote_update = FileFileRemote(name="pass_test", url="http://")
        response = self.remotes_api.update(href, remote_update)
        monitor_task(response.task)
        exc = cli_client.run(["pulpcore-manager", "shell", "-c", shell_cmd])
        self.assertEqual(exc.stdout.rstrip("\n"), "new")

    def test_timeout_attributes(self):
        # Test valid timeout settings (float >= 0)
        data = {
            "total_timeout": 1.0,
            "connect_timeout": 66.0,
            "sock_connect_timeout": 0.0,
            "sock_read_timeout": 3.1415926535,
        }
        self.remotes_api.partial_update(self.remote.pulp_href, data)
        time.sleep(1)
        new_remote = self.remotes_api.read(self.remote.pulp_href)
        self._compare_results(data, new_remote)

    def test_timeout_attributes_float_lt_zero(self):
        # Test invalid float < 0
        data = {
            "total_timeout": -1.0,
        }
        with self.assertRaises(ApiException):
            self.remotes_api.partial_update(self.remote.pulp_href, data)

    def test_timeout_attributes_non_float(self):
        # Test invalid non-float
        data = {
            "connect_timeout": "abc",
        }
        with self.assertRaises(ApiException):
            self.remotes_api.partial_update(self.remote.pulp_href, data)

    def test_timeout_attributes_reset_to_empty(self):
        # Test reset to empty
        data = {
            "total_timeout": False,
            "connect_timeout": None,
            "sock_connect_timeout": False,
            "sock_read_timeout": None,
        }
        response = self.remotes_api.partial_update(self.remote.pulp_href, data)
        monitor_task(response.task)
        new_remote = self.remotes_api.read(self.remote.pulp_href)
        self._compare_results(data, new_remote)

    def test_delete(self):
        response = self.remotes_api.delete(self.remote.pulp_href)
        monitor_task(response.task)
        # verify the delete
        with self.assertRaises(ApiException):
            self.remotes_api.read(self.remote.pulp_href)

    def test_headers(self):
        # Test that headers value must be a list of dicts
        data = {"headers": {"Connection": "keep-alive"}}
        with self.assertRaises(ApiException):
            self.remotes_api.partial_update(self.remote.pulp_href, data)
        data = {"headers": [1, 2, 3]}
        with self.assertRaises(ApiException):
            self.remotes_api.partial_update(self.remote.pulp_href, data)
        data = {"headers": [{"Connection": "keep-alive"}]}
        self.remotes_api.partial_update(self.remote.pulp_href, data)


class CreatePulpLabelsRemoteTestCase(unittest.TestCase):
    """A test case for verifying whether pulp_labels are correctly assigned to a new remote."""

    @classmethod
    def setUpClass(cls):
        """Initialize class-wide variables"""
        cls.cfg = config.get_config()

        cls.api_client = api.Client(cls.cfg, api.json_handler)
        cls.file_client = FileApiClient(cls.cfg.get_bindings_config())
        cls.remotes_api = RemotesFileApi(cls.file_client)

        cls.pulp_labels = {"environment": "dev"}

    def test_create_remote(self):
        """Test if a created remote contains pulp_labels when passing JSON data."""
        remote_attrs = {
            "name": utils.uuid4(),
            "url": FILE_FIXTURE_MANIFEST_URL,
            "pulp_labels": self.pulp_labels,
        }
        remote = self.remotes_api.create(remote_attrs)
        self.addCleanup(self.remotes_api.delete, remote.pulp_href)

        self.assertEqual(remote.pulp_labels, self.pulp_labels)

    def test_create_remote_using_form(self):
        """Test if a created remote contains pulp_labels when passing form data."""
        remote_attrs = {
            "name": utils.uuid4(),
            "url": FILE_FIXTURE_MANIFEST_URL,
            "pulp_labels": json.dumps(self.pulp_labels),
        }
        remote = self.api_client.post(FILE_REMOTE_PATH, data=remote_attrs)
        self.addCleanup(self.remotes_api.delete, remote["pulp_href"])
        self.assertEqual(remote["pulp_labels"], self.pulp_labels)


class RemoteFileURLsValidationTestCase(unittest.TestCase):
    """A test case that verifies the validation of remotes' URLs."""

    @classmethod
    def setUpClass(cls):
        """Initialize class-wide variables"""
        cls.cfg = config.get_config()

        cls.api_client = api.Client(cls.cfg, api.json_handler)
        cls.file_client = FileApiClient(cls.cfg.get_bindings_config())
        cls.remotes_api = RemotesFileApi(cls.file_client)

    def test_invalid_absolute_pathname(self):
        """Test the validation of an invalid absolute pathname."""
        remote_attrs = {
            "name": utils.uuid4(),
            "url": "file://error/path/name",
        }
        self.raise_for_invalid_request(remote_attrs)

    def test_invalid_import_path(self):
        """Test the validation of an invalid import pathname."""
        remote_attrs = {
            "name": utils.uuid4(),
            "url": "file:///error/path/name",
        }
        self.raise_for_invalid_request(remote_attrs)

    def raise_for_invalid_request(self, remote_attrs):
        """Check if Pulp returns HTTP 400 after issuing an invalid request."""
        with self.assertRaises(ApiException) as ae:
            remote = self.remotes_api.create(remote_attrs)
            self.addCleanup(self.remotes_api.delete, remote.pulp_href)

        self.assertEqual(ae.exception.status, 400)

    def test_valid_import_path(self):
        """Test the creation of a remote after passing a valid URL."""
        remote_attrs = {
            "name": utils.uuid4(),
            "url": "file:///tmp/good",
        }

        remote = self.remotes_api.create(remote_attrs)
        self.addCleanup(self.remotes_api.delete, remote.pulp_href)
