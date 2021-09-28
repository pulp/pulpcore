from importlib import import_module
from unittest.mock import Mock

from django.test import TestCase

from pulpcore.app.models import Remote


class TestMoveRemoteUrlCredentialsMigration(TestCase):
    """Test the move remote url credentials migration."""

    def setUp(self):
        self.remote = Remote.objects.create(
            name="test-url", url="http://elladan:lembas@rivendell.org", pulp_type="file"
        )

    def tearDown(self):
        self.remote.delete()

    def test_move_remote_url_credentials(self):
        apps_mock = Mock()
        apps_mock.get_model = Mock(return_value=Remote)

        # use import_module due to underscores
        migration = import_module("pulpcore.app.migrations.0077_move_remote_url_credentials")
        migration.move_remote_url_credentials(apps_mock, None)

        self.remote = Remote.objects.get(name="test-url")
        self.assertEqual(self.remote.url, "http://rivendell.org")
        self.assertEqual(self.remote.username, "elladan")
        self.assertEqual(self.remote.password, "lembas")
