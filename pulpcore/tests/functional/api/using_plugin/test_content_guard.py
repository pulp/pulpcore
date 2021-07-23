import requests
import unittest

from urllib.parse import urljoin

from pulp_smash import config, utils
from pulp_smash.pulp3.bindings import monitor_task
from pulp_smash.pulp3.utils import gen_distribution
from pulpcore.tests.functional.api.using_plugin.constants import PULP_CONTENT_BASE_URL
from pulpcore.tests.functional.api.using_plugin.utils import gen_file_client, gen_user, del_user
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

    @classmethod
    def setUpClass(cls):
        """Set up test variables"""
        client = gen_file_client()  # This is admin client, following apis are for admin user
        core_client = CoreApiClient(config.get_config().get_bindings_config())
        cls.groups_api = GroupsApi(core_client)
        cls.group_users_api = GroupsUsersApi(core_client)
        cls.distro_api = DistributionsFileApi(client)
        response = monitor_task(cls.distro_api.create(gen_distribution()).task)
        cls.distro = cls.distro_api.read(response.created_resources[0])
        cls.rbac_guard_api = ContentguardsRbacApi(client)

        cls.admin = {
            "username": client.configuration.username,
            "password": client.configuration.password,
        }
        user = gen_user(model_permissions=["core.add_rbaccontentguard"])
        user["rbac_guard_api"] = ContentguardsRbacApi(user["core_api_client"])
        cls.creator_user = user
        cls.user_a = gen_user()
        cls.user_b = gen_user()
        cls.all_users = [cls.creator_user, cls.user_a, cls.user_a, cls.admin, None]

        cls.group = cls.groups_api.create({"name": utils.uuid4()})
        cls.group_users_api.create(cls.group.pulp_href, {"username": cls.user_b["username"]})
        cls.group_users_api.create(cls.group.pulp_href, {"username": cls.user_a["username"]})

        cls.url = urljoin(PULP_CONTENT_BASE_URL, f"{cls.distro.base_path}/")

    @classmethod
    def tearDownClass(cls):
        """Clean up all class variables"""
        cls.distro_api.delete(cls.distro.pulp_href)
        cls.rbac_guard_api.delete(cls.distro.content_guard)
        cls.groups_api.delete(cls.group.pulp_href)
        del_user(cls.creator_user)
        del_user(cls.user_a)
        del_user(cls.user_b)

    def test_01_all_users_access(self):
        """Sanity check that all users can access distribution with no content guard"""
        self.assert_access(self.all_users)

    def test_02_content_guard_creation(self):
        """Checks that RBAC ContentGuard can be created and assigned to a distribution"""
        guard = self.creator_user["rbac_guard_api"].create({"name": self.distro.name})
        body = PatchedfileFileDistribution(content_guard=guard.pulp_href)
        monitor_task(self.distro_api.partial_update(self.distro.pulp_href, body).task)
        RBACContentGuardTestCase.distro = self.distro_api.read(self.distro.pulp_href)
        self.assertEqual(guard.pulp_href, self.distro.content_guard)

    def test_03_only_creator_access(self):
        """Checks that now only the creator and admin user can access the distribution"""
        self.assert_access([self.creator_user, self.admin])

    def test_04_add_users(self):
        """Use the /add/ endpoint to give the users permission to access distribution"""
        body = {"usernames": (self.user_a["username"], self.user_b["username"])}
        self.creator_user["rbac_guard_api"].assign_permission(self.distro.content_guard, body)
        self.assert_access([self.creator_user, self.user_b, self.user_a, self.admin])

    def test_05_remove_users(self):
        """Use the /remove/ endpoint to remove users permission to access distribution"""
        body = {"usernames": (self.user_a["username"], self.user_b["username"])}
        self.creator_user["rbac_guard_api"].remove_permission(self.distro.content_guard, body)
        self.assert_access([self.creator_user, self.admin])

    def test_06_add_group(self):
        """Use the /add/ endpoint to add group"""
        body = {"groupnames": [self.group.name]}
        self.creator_user["rbac_guard_api"].assign_permission(self.distro.content_guard, body)
        self.assert_access([self.creator_user, self.user_b, self.user_a, self.admin])

    def test_07_remove_group(self):
        """Use the /remove/ endpoint to remove group"""
        body = {"groupnames": [self.group.name]}
        self.creator_user["rbac_guard_api"].remove_permission(self.distro.content_guard, body)
        self.assert_access([self.creator_user, self.admin])

    def assert_access(self, auth_users):
        """Helper for asserting functionality and correct permissions on the content guard"""
        for user in self.all_users:
            auth = (user["username"], user["password"]) if user else None
            r = requests.session()
            r.trust_env = False  # Don't read the .netrc file
            response = r.get(self.url, auth=auth)
            expected_status = 404 if user in auth_users else 403
            self.assertEqual(response.status_code, expected_status, f"Failed on {user=}")
