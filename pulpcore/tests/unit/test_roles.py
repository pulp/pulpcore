from unittest import TestCase
from unittest.mock import Mock

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from guardian.shortcuts import assign_perm, get_objects_for_user, get_objects_for_group, remove_perm

User = get_user_model()

from pulpcore.app.apps import _handle_role_definition_changes
from pulpcore.app.models import ProgressReport, RoleHistory, Task
from pulpcore.app.roles import assign_role, remove_role, Role


class FakeRole(Role):
    permissions = [
        "core.view_task",
        "core.change_task",
        "core.view_progressreport",
        "core.change_progressreport"
    ]


class BaseRoleTestCase(TestCase):
    def setUp(self):
        self.fake_sender = Mock()
        self.fake_sender.roles = [FakeRole]
        self.fake_role_name = 'pulpcore.tests.unit.test_roles.FakeRole'
        self.fake_sender.roles[0].permissions = [
            "core.view_task",
            "core.change_task",
            "core.view_progressreport",
            "core.change_progressreport"
        ]
        _handle_role_definition_changes(self.fake_sender)
        self.user_a = User.objects.create_user('user_a', 'user_a@example.com', 'password')
        self.user_b = User.objects.create_user('user_b', 'user_a@example.com', 'password')
        self.group_a = Group.objects.create(name='group_a')
        self.group_b = Group.objects.create(name='group_b')
        self.group_a.user_set.add(self.user_a)
        self.group_b.user_set.add(self.user_b)
        self.task_foo = Task.objects.create()
        self.progress_report_foo = ProgressReport.objects.create(task_id=self.task_foo.pk)
        self.task_bar = Task.objects.create()
        self.progress_report_bar = ProgressReport.objects.create(task_id=self.task_bar.pk)


    def tearDown(self):
        RoleHistory.objects.get(role_obj_classpath=self.fake_role_name).delete()
        self.progress_report_bar.delete()
        self.task_bar.delete()
        self.progress_report_foo.delete()
        self.task_foo.delete()
        self.group_b.delete()
        self.group_a.delete()
        self.user_b.delete()
        self.user_a.delete()


class TestAssignRoleFunctions(BaseRoleTestCase):

    def test_assign_role_to_user_no_obj(self):
        assign_role(FakeRole, self.user_a)
        self.assertEqual(self.user_a.get_all_permissions(), set(FakeRole.permissions))
        self.assertEqual(self.user_b.get_all_permissions(), set())

    def test_assign_role_to_group_no_obj(self):
        assign_role(FakeRole, self.group_a)
        self.assertEqual(self.user_a.get_all_permissions(), set(FakeRole.permissions))
        self.assertEqual(self.user_b.get_all_permissions(), set())

    def test_assign_role_to_user_with_obj(self):
        assign_role(FakeRole, self.user_a, self.task_foo)

        qs_user_objects = get_objects_for_user(self.user_a, ["core.view_task", "core.change_task"])
        self.assertEqual(qs_user_objects.count(), 1)

        qs_user_objects = get_objects_for_user(self.user_a, [
            "core.view_progressreport", "core.change_progressreport"
        ])
        self.assertEqual(qs_user_objects.count(), 0)

    def test_assign_role_to_group_with_obj(self):
        assign_role(FakeRole, self.group_a, self.task_foo)

        qs_user_objects = get_objects_for_user(self.user_a, ["core.view_task", "core.change_task"])
        self.assertEqual(qs_user_objects.count(), 1)

        qs_user_objects = get_objects_for_user(self.user_a, [
            "core.view_progressreport", "core.change_progressreport"
        ])
        self.assertEqual(qs_user_objects.count(), 0)


class TestRemoveRoleFunctions(BaseRoleTestCase):

    def test_remove_role_from_user_no_obj(self):
        assign_role(FakeRole, self.user_a)
        remove_role(FakeRole, self.user_a)
        self.assertEqual(self.user_a.get_all_permissions(), set())
        self.assertEqual(self.user_b.get_all_permissions(), set())

    def test_remove_role_from_group_no_obj(self):
        assign_role(FakeRole, self.group_a)
        remove_role(FakeRole, self.group_a)
        self.assertEqual(self.user_a.get_all_permissions(), set())
        self.assertEqual(self.user_b.get_all_permissions(), set())

    def test_remove_role_from_user_with_obj(self):
        assign_role(FakeRole, self.user_a, self.task_foo)
        remove_role(FakeRole, self.user_a, self.task_foo)

        qs_user_objects = get_objects_for_user(self.user_a, ["core.view_task", "core.change_task"])
        self.assertEqual(qs_user_objects.count(), 0)

        qs_user_objects = get_objects_for_user(self.user_a, [
            "core.view_progressreport", "core.change_progressreport"
        ])
        self.assertEqual(qs_user_objects.count(), 0)

    def test_remove_role_from_group_with_obj(self):
        assign_role(FakeRole, self.group_a, self.task_foo)
        remove_role(FakeRole, self.group_a, self.task_foo)

        qs_user_objects = get_objects_for_user(self.user_a, ["core.view_task", "core.change_task"])
        self.assertEqual(qs_user_objects.count(), 0)

        qs_user_objects = get_objects_for_user(self.user_a, [
            "core.view_progressreport", "core.change_progressreport"
        ])
        self.assertEqual(qs_user_objects.count(), 0)


class TestRoleHistory(BaseRoleTestCase):

    def test_new_role_has_role_history_created(self):
        role_history_entry= RoleHistory.objects.get(role_obj_classpath=self.fake_role_name)
        self.assertEqual(set(FakeRole.permissions), set(role_history_entry.permissions))

    def test_permissions_added_user_no_obj(self):
        # Ensure a user with not all perms doesn't receive more
        assign_perm("core.view_task", self.user_b)

        assign_role(FakeRole, self.user_a)  # user_a has all the perms in the role

        additional_perms = ["core.delete_task", "core.add_task", "core.delete_progressreport"]
        self.fake_sender.roles[0].permissions.extend(additional_perms)
        _handle_role_definition_changes(self.fake_sender)

        expected_perms = set(FakeRole.permissions + additional_perms)
        self.assertEqual(self.user_a.get_all_permissions(), expected_perms)
        self.assertEqual(self.user_b.get_all_permissions(), set(["core.view_task"]))

    def test_permissions_added_group_no_obj(self):
        # Ensure a group with not all perms doesn't receive more
        assign_perm("core.view_task", self.group_b)

        assign_role(FakeRole, self.group_a)  # group_a has all the perms in the role

        additional_perms = ["core.delete_task", "core.add_task", "core.delete_progressreport"]
        self.fake_sender.roles[0].permissions.extend(additional_perms)
        _handle_role_definition_changes(self.fake_sender)

        expected_perms = set(FakeRole.permissions + additional_perms)
        self.assertEqual(self.user_a.get_all_permissions(), expected_perms)
        self.assertEqual(self.user_b.get_all_permissions(), set(["core.view_task"]))

    def test_permissions_added_user_with_obj(self):
        # Ensure a user with not all perms on an object doesn't receive more
        assign_perm("core.view_task", self.user_b, self.task_foo)

        assign_role(FakeRole, self.user_a, self.task_foo)  # user_a has all the perms in the role

        self.fake_sender.roles[0].permissions.extend(
            ["core.delete_task", "core.add_task", "core.delete_progressreport"]
        )
        _handle_role_definition_changes(self.fake_sender)

        self.assertEqual(self.user_a.get_all_permissions(), set())
        self.assertEqual(self.user_b.get_all_permissions(), set())

        qs_user_objects = get_objects_for_user(
            self.user_a, ["core.view_task", "core.change_task", "core.delete_task", "core.add_task"]
        )
        self.assertEqual(qs_user_objects.count(), 1)

        qs_user_objects = get_objects_for_user(
            self.user_b, ["core.view_task", "core.change_task", "core.delete_task", "core.add_task"]
        )
        self.assertEqual(qs_user_objects.count(), 0)

        qs_user_objects = get_objects_for_user(self.user_a, [
            "core.view_progressreport", "core.change_progressreport", "core.delete_progressreport"
        ])
        self.assertEqual(qs_user_objects.count(), 0)

    def test_permissions_added_group_with_obj(self):
        # Ensure a group with not all perms on an object doesn't receive more
        assign_perm("core.view_task", self.group_b, self.task_foo)

        assign_role(FakeRole, self.group_a, self.task_foo)  # group_a has all the perms in the role

        self.fake_sender.roles[0].permissions.extend(
            ["core.delete_task", "core.add_task", "core.delete_progressreport"]
        )
        _handle_role_definition_changes(self.fake_sender)

        self.assertEqual(self.user_a.get_all_permissions(), set())
        self.assertEqual(self.user_b.get_all_permissions(), set())

        qs_group_objects = get_objects_for_group(
            self.group_a, ["core.view_task", "core.change_task", "core.delete_task", "core.add_task"]
        )
        self.assertEqual(qs_group_objects.count(), 1)

        qs_group_objects = get_objects_for_group(
            self.group_b, ["core.view_task", "core.change_task", "core.delete_task", "core.add_task"]
        )
        self.assertEqual(qs_group_objects.count(), 0)

        qs_group_objects = get_objects_for_group(self.group_a, [
            "core.view_progressreport", "core.change_progressreport", "core.delete_progressreport"
        ])
        self.assertEqual(qs_group_objects.count(), 0)

    def test_permissions_removed_user_no_obj(self):
        # Ensure a user with not all perms doesn't have them removed
        assign_perm("core.view_task", self.user_b)

        assign_role(FakeRole, self.user_a)  # user_a has all the perms in the role

        self.fake_sender.roles[0].permissions = ["core.view_progressreport"]

        _handle_role_definition_changes(self.fake_sender)

        self.assertEqual(self.user_a.get_all_permissions(), set(["core.view_progressreport"]))
        self.assertEqual(self.user_b.get_all_permissions(), set(["core.view_task"]))

    def test_permissions_removed_group_no_obj(self):
        # Ensure a group with not all perms doesn't receive more
        assign_perm("core.view_task", self.group_b)

        assign_role(FakeRole, self.group_a)  # group_a has all the perms in the role

        self.fake_sender.roles[0].permissions = ["core.view_progressreport"]

        _handle_role_definition_changes(self.fake_sender)

        self.assertEqual(self.user_a.get_all_permissions(), set(["core.view_progressreport"]))
        self.assertEqual(self.user_b.get_all_permissions(), set(["core.view_task"]))

    def test_permissions_removed_user_with_obj(self):
        # Ensure a user with not all perms on an object doesn't have them removed
        assign_perm("core.view_task", self.user_b, self.task_foo)

        assign_role(FakeRole, self.user_a, self.task_foo)  # user_a has all the perms in the role

        self.fake_sender.roles[0].permissions = ["core.change_task"]
        _handle_role_definition_changes(self.fake_sender)

        self.assertEqual(self.user_a.get_all_permissions(), set())
        self.assertEqual(self.user_b.get_all_permissions(), set())

        qs_user_objects = get_objects_for_user(self.user_a, ["core.change_task"])
        self.assertEqual(qs_user_objects.count(), 1)

        qs_user_objects = get_objects_for_user(
            self.user_a, ["core.view_task", "core.change_task"]
        )
        self.assertEqual(qs_user_objects.count(), 0)

        qs_user_objects = get_objects_for_user(self.user_b, ["core.view_task"])
        self.assertEqual(qs_user_objects.count(), 1)

    def test_permissions_removed_group_with_obj(self):
        # Ensure a group with not all perms on an object doesn't have them removed
        assign_perm("core.view_task", self.group_b, self.task_foo)

        assign_role(FakeRole, self.group_a, self.task_foo)  # group_a has all the perms in the role

        self.fake_sender.roles[0].permissions = ["core.change_task"]
        _handle_role_definition_changes(self.fake_sender)

        self.assertEqual(self.user_a.get_all_permissions(), set())
        self.assertEqual(self.user_b.get_all_permissions(), set())

        qs_group_objects = get_objects_for_group(self.group_a, ["core.change_task"])
        self.assertEqual(qs_group_objects.count(), 1)

        qs_group_objects = get_objects_for_group(
            self.group_a, ["core.view_task", "core.change_task"]
        )
        self.assertEqual(qs_group_objects.count(), 0)

        qs_group_objects = get_objects_for_group(self.group_b, ["core.view_task"])
        self.assertEqual(qs_group_objects.count(), 1)
