import unittest


from pulp_smash import api, cli, config

from pulpcore.client.pulpcore import ApiClient, GroupsApi, UsersApi


class UserTestCase(unittest.TestCase):
    """Test REST API for users."""

    @classmethod
    def setUpClass(cls):
        cls.cfg = config.get_config()
        cls.client = api.Client(cls.cfg, api.json_handler)
        cls.client = ApiClient(
            configuration=cls.cfg.get_bindings_config(),
        )
        cls.cli_client = cli.Client(cls.cfg)

        cls.user_api = UsersApi(cls.client)

    def test_list_users(self):
        """Test that users can be listed."""
        users = self.user_api.list()
        self.assertIn("admin", [user.username for user in users.results])

    def test_filter_users(self):
        """Test that users can be filterd."""
        users = self.user_api.list(username="admin")
        self.assertEqual(len(users.results), 1)


class GroupTestCase(unittest.TestCase):
    """Test REST API for users."""

    @classmethod
    def setUpClass(cls):
        cls.cfg = config.get_config()
        cls.client = api.Client(cls.cfg, api.json_handler)
        cls.client = ApiClient(
            configuration=cls.cfg.get_bindings_config(),
        )
        cls.cli_client = cli.Client(cls.cfg)

        cls.group_api = GroupsApi(cls.client)

    def test_list_groups(self):
        """Test that a group can be crud."""

        groups = self.group_api.list()
        self.assertNotIn("test_newbees", [group.name for group in groups.results])
        group_href = self.group_api.create(group={"name": "test_newbees"}).pulp_href
        try:
            groups = self.group_api.list()
            self.assertIn("test_newbees", [group.name for group in groups.results])
        finally:
            self.group_api.delete(group_href)
        groups = self.group_api.list()
        self.assertNotIn("test_newbees", [group.name for group in groups.results])

    def test_filter_users(self):
        """Test that groups can be filterd."""

        groups = self.group_api.list(name__contains="test_")
        self.assertEqual(len(groups.results), 0)

        group_hrefs = [
            self.group_api.create(group={"name": name}).pulp_href
            for name in ["test_newbees", "test_admins"]
        ]
        try:
            groups = self.group_api.list(name__contains="test_")
            self.assertEqual(len(groups.results), 2)
            groups = self.group_api.list(name__contains="test_new")
            self.assertEqual(len(groups.results), 1)
            groups = self.group_api.list(name="test_newbees")
            self.assertEqual(len(groups.results), 1)
        finally:
            for group_href in group_hrefs:
                self.group_api.delete(group_href)
