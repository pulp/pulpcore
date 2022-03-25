import requests
import unittest

from urllib.parse import urljoin

from pulp_smash import config, utils
from pulp_smash.pulp3.bindings import monitor_task
from pulp_smash.pulp3.utils import gen_distribution
from pulpcore.tests.functional.api.using_plugin.constants import PULP_CONTENT_BASE_URL
from pulpcore.tests.functional.api.using_plugin.utils import (
    gen_file_client,
    gen_user_rest,
    del_user_rest,
)
from pulpcore.client.pulpcore import (
    ApiClient as CoreApiClient,
    GroupsApi,
    GroupsUsersApi,
    ContentguardsRbacApi,
)
from pulpcore.client.pulp_file import (
    DistributionsFileApi,
    PatchedfileFileDistribution,
)

from pulpcore.tests.functional.api.using_plugin.utils import (  # noqa:F401
    set_up_module as setUpModule,
)


class RBACContentGuardTestCase(unittest.TestCase):
    """Test RBAC enabled content guard"""

    CREATOR_ROLE = "core.rbaccontentguard_creator"
    DOWNLOAD_ROLE = "core.rbaccontentguard_downloader"

    @classmethod
    def setUpClass(cls):
        cls.client = gen_file_client()  # This is admin client, following apis are for admin user
        cls.api_config = config.get_config().get_bindings_config()
        core_client = CoreApiClient(config.get_config().get_bindings_config())
        cls.groups_api = GroupsApi(core_client)
        cls.group_users_api = GroupsUsersApi(core_client)
        cls.distro_api = DistributionsFileApi(cls.client)

    def setUp(self):
        response = monitor_task(self.distro_api.create(gen_distribution()).task)
        self.distro = self.distro_api.read(response.created_resources[0])
        self.rbac_guard_api = ContentguardsRbacApi(self.client)

        self.admin = {
            "username": self.client.configuration.username,
            "password": self.client.configuration.password,
        }
        user = gen_user_rest(model_roles=["core.rbaccontentguard_creator"])
        self.api_config.username = user["username"]
        self.api_config.password = user["password"]
        user["rbac_guard_api"] = ContentguardsRbacApi(CoreApiClient(self.api_config))
        self.creator_user = user
        self.user_a = gen_user_rest()
        self.user_b = gen_user_rest()
        self.all_users = [self.creator_user, self.user_a, self.user_a, self.admin, None]

        self.group = self.groups_api.create({"name": utils.uuid4()})
        self.group_users_api.create(self.group.pulp_href, {"username": self.user_b["username"]})
        self.group_users_api.create(self.group.pulp_href, {"username": self.user_a["username"]})

        self.url = urljoin(PULP_CONTENT_BASE_URL, f"{self.distro.base_path}/")

    def tearDown(self):
        self.distro_api.delete(self.distro.pulp_href)
        self.rbac_guard_api.delete(self.distro.content_guard)
        self.groups_api.delete(self.group.pulp_href)
        del_user_rest(self.creator_user["pulp_href"])
        del_user_rest(self.user_a["pulp_href"])
        del_user_rest(self.user_b["pulp_href"])

    def test_workflow(self):
        self._all_users_access()
        self._content_guard_creation()
        self._only_creator_access()
        self._add_users()
        self._remove_users()
        self._add_group()
        self._remove_group()

    def _all_users_access(self):
        """Sanity check that all users can access distribution with no content guard"""
        self._assert_access(self.all_users)

    def _content_guard_creation(self):
        """Checks that RBAC ContentGuard can be created and assigned to a distribution"""
        guard = self.creator_user["rbac_guard_api"].create({"name": self.distro.name})
        body = PatchedfileFileDistribution(content_guard=guard.pulp_href)
        monitor_task(self.distro_api.partial_update(self.distro.pulp_href, body).task)
        self.distro = self.distro_api.read(self.distro.pulp_href)
        self.assertEqual(guard.pulp_href, self.distro.content_guard)

    def _only_creator_access(self):
        """Checks that now only the creator and admin user can access the distribution"""
        self._assert_access([self.creator_user, self.admin])

    def _add_users(self):
        """Use the /add/ endpoint to give the users permission to access distribution"""
        body = {
            "users": (self.user_a["username"], self.user_b["username"]),
            "role": self.DOWNLOAD_ROLE,
        }
        self.creator_user["rbac_guard_api"].add_role(self.distro.content_guard, body)
        self._assert_access([self.creator_user, self.user_b, self.user_a, self.admin])

    def _remove_users(self):
        """Use the /remove/ endpoint to remove users permission to access distribution"""
        body = {
            "users": (self.user_a["username"], self.user_b["username"]),
            "role": self.DOWNLOAD_ROLE,
        }
        self.creator_user["rbac_guard_api"].remove_role(self.distro.content_guard, body)
        self._assert_access([self.creator_user, self.admin])

    def _add_group(self):
        """Use the /add/ endpoint to add group"""
        body = {"groups": [self.group.name], "role": self.DOWNLOAD_ROLE}
        self.creator_user["rbac_guard_api"].add_role(self.distro.content_guard, body)
        self._assert_access([self.creator_user, self.user_b, self.user_a, self.admin])

    def _remove_group(self):
        """Use the /remove/ endpoint to remove group"""
        body = {"groups": [self.group.name], "role": self.DOWNLOAD_ROLE}
        self.creator_user["rbac_guard_api"].remove_role(self.distro.content_guard, body)
        self._assert_access([self.creator_user, self.admin])

    def _assert_access(self, auth_users):
        """Helper for asserting functionality and correct permissions on the content guard"""
        for user in self.all_users:
            auth = (user["username"], user["password"]) if user else None
            r = requests.session()
            r.trust_env = False  # Don't read the .netrc file
            response = r.get(self.url, auth=auth)
            expected_status = 404 if user in auth_users else 403
            self.assertEqual(response.status_code, expected_status, f"Failed on {user=}")
