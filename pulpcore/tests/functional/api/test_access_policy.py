"""Tests related to the AccessPolicy."""

import unittest

from pulp_smash import config

from pulpcore.client.pulpcore import (
    ApiClient as CoreApiClient,
    AccessPoliciesApi,
)


class AccessPolicyTestCase(unittest.TestCase):
    """
    Test cases for AccessPolicy.
    """

    @classmethod
    def setUpClass(cls):
        """Create class-wide variables."""
        cls.cfg = config.get_config()
        cls.core_client = CoreApiClient(configuration=cls.cfg.get_bindings_config())
        cls.access_policy_api = AccessPoliciesApi(cls.core_client)

    def test_access_policy_cannot_be_created(self):
        """Test that only plugin writers can ship a new AccessPolicy."""
        self.assertFalse(hasattr(self.access_policy_api, "create"))

    def test_access_policy_default_policies(self):
        """Test that the default policies from pulpcore are installed."""
        groups_response = self.access_policy_api.list(viewset_name="groups")
        self.assertEqual(groups_response.count, 1)

        groups_users_response = self.access_policy_api.list(viewset_name="groups/users")
        self.assertEqual(groups_users_response.count, 1)

        tasks_response = self.access_policy_api.list(viewset_name="tasks")
        self.assertEqual(tasks_response.count, 1)

    def test_statements_attr_can_be_modified(self):
        """Test that `AccessPolicy.statements` can be modified"""
        tasks_response = self.access_policy_api.list(viewset_name="tasks")
        tasks_href = tasks_response.results[0].pulp_href
        task_access_policy = self.access_policy_api.read(tasks_href)

        original_statements = task_access_policy.statements
        self.assertFalse(task_access_policy.customized)
        self.assertNotEqual(original_statements, [])

        self.access_policy_api.partial_update(tasks_href, {"statements": []})
        task_access_policy = self.access_policy_api.read(tasks_href)
        self.assertTrue(task_access_policy.customized)
        self.assertEqual(task_access_policy.statements, [])

        self.access_policy_api.partial_update(tasks_href, {"statements": original_statements})
        task_access_policy = self.access_policy_api.read(tasks_href)
        self.assertTrue(task_access_policy.customized)
        self.assertEqual(task_access_policy.statements, original_statements)

    def test_permissions_assignment_attr_can_be_modified(self):
        """Test that `AccessPolicy.permissions_assignment` can be modified"""
        groups_response = self.access_policy_api.list(viewset_name="groups")
        groups_href = groups_response.results[0].pulp_href
        groups_access_policy = self.access_policy_api.read(groups_href)

        original_permissions_assignment = groups_access_policy.permissions_assignment
        self.assertFalse(groups_access_policy.customized)
        self.assertNotEqual(original_permissions_assignment, [])

        self.access_policy_api.partial_update(groups_href, {"permissions_assignment": []})
        groups_access_policy = self.access_policy_api.read(groups_href)
        self.assertTrue(groups_access_policy.customized)
        self.assertEqual(groups_access_policy.permissions_assignment, [])

        self.access_policy_api.partial_update(
            groups_href, {"permissions_assignment": original_permissions_assignment}
        )
        groups_access_policy = self.access_policy_api.read(groups_href)
        self.assertTrue(groups_access_policy.customized)
        self.assertEqual(
            groups_access_policy.permissions_assignment, original_permissions_assignment
        )

    def test_customized_is_read_only(self):
        """Test that the `AccessPolicy.customized` attribute is read only"""
        tasks_response = self.access_policy_api.list(viewset_name="tasks")
        tasks_href = tasks_response.results[0].pulp_href
        task_access_policy = self.access_policy_api.read(tasks_href)

        response = self.access_policy_api.partial_update(
            tasks_href, {"customized": not task_access_policy.customized}
        )
        self.assertEqual(response.customized, task_access_policy.customized)

    def test_viewset_name_is_read_only(self):
        """Test that the `AccessPolicy.viewset_name` attribute is read only"""
        tasks_response = self.access_policy_api.list(viewset_name="tasks")
        tasks_href = tasks_response.results[0].pulp_href
        task_access_policy = self.access_policy_api.read(tasks_href)

        response = self.access_policy_api.partial_update(
            tasks_href, {"viewset_name": "not-a-real-name"}
        )
        self.assertEqual(response.viewset_name, task_access_policy.viewset_name)
