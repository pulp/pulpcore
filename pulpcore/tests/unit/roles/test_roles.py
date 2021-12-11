from uuid import uuid4

from django.test import TestCase

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission

from pulpcore.app.models import Group, Remote, Repository
from pulpcore.app.models.role import Role
from pulpcore.app.role_util import assign_role, remove_role, get_objects_for_user


User = get_user_model()


class UserRoleTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create(username=uuid4())
        self.group = Group.objects.create(name=uuid4())
        self.group.user_set.add(self.user)
        self.role1 = Role.objects.create(name="role1")
        self.role1.permissions.add(
            Permission.objects.get(content_type__app_label="core", codename="view_repository")
        )
        self.role2 = Role.objects.create(name="role2")
        self.role2.permissions.add(
            Permission.objects.get(content_type__app_label="core", codename="view_remote")
        )
        self.repository = Repository.objects.create(name=uuid4())
        self.repository2 = Repository.objects.create(name=uuid4())
        self.remote = Remote.objects.create(name=uuid4())
        self.remote2 = Remote.objects.create(name=uuid4())

    def test_user_no_role(self):
        self.assertFalse(self.user.has_perm("core.view_repository"))
        self.assertFalse(self.user.has_perm("core.view_repository", self.repository))
        self.assertFalse(self.user.has_perm("core.view_remote"))
        self.assertFalse(self.user.has_perm("core.view_remote", self.remote))
        self.assertEqual(self.user.get_all_permissions(), set())
        self.assertEqual(self.user.get_all_permissions(self.repository), set())

    def test_user_object_role(self):
        assign_role("role1", self.user, self.repository)
        self.assertFalse(self.user.has_perm("core.view_repository"))
        self.assertTrue(self.user.has_perm("core.view_repository", self.repository))
        self.assertEqual(self.user.get_all_permissions(), set())
        self.assertEqual(self.user.get_all_permissions(self.repository), {"view_repository"})
        remove_role("role1", self.user, self.repository)

    def test_user_role(self):
        assign_role("role1", self.user)
        self.assertTrue(self.user.has_perm("core.view_repository"))
        self.assertFalse(self.user.has_perm("core.view_repository", self.repository))
        self.assertEqual(self.user.get_all_permissions(), {"core.view_repository"})
        self.assertEqual(self.user.get_all_permissions(self.repository), set())
        remove_role("role1", self.user)

    def test_group_object_role(self):
        assign_role("role2", self.group, self.remote)
        self.assertFalse(self.user.has_perm("core.view_remote"))
        self.assertTrue(self.user.has_perm("core.view_remote", self.remote))
        self.assertEqual(self.user.get_all_permissions(), set())
        self.assertEqual(self.user.get_all_permissions(self.remote), {"view_remote"})
        remove_role("role2", self.group, self.remote)

    def test_group_role(self):
        assign_role("role2", self.group)
        self.assertTrue(self.user.has_perm("core.view_remote"))
        self.assertFalse(self.user.has_perm("core.view_remote", self.remote))
        self.assertEqual(self.user.get_all_permissions(), {"core.view_remote"})
        self.assertEqual(self.user.get_all_permissions(self.remote), set())
        remove_role("role2", self.group)

    def test_combination_role(self):
        assign_role("role1", self.user, self.repository)
        assign_role("role2", self.group)
        self.assertEqual(self.user.get_all_permissions(), {"core.view_remote"})
        self.assertEqual(self.user.get_all_permissions(self.repository), {"view_repository"})
        self.assertEqual(self.user.get_all_permissions(self.remote), set())
        self.assertEqual(
            set(
                get_objects_for_user(
                    self.user, "core.view_repository", Repository.objects.all()
                ).values_list("pk", flat=True)
            ),
            {self.repository.pk},
        )
        self.assertEqual(
            set(
                get_objects_for_user(
                    self.user, "core.view_remote", Remote.objects.all()
                ).values_list("pk", flat=True)
            ),
            {self.remote.pk, self.remote2.pk},
        )
        remove_role("role2", self.group)
