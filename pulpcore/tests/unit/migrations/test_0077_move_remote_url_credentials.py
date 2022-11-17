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
        self.remote_without_credentials = Remote.objects.create(
            name="test-url-no-credentials", url="https://download.copr.fedorainfracloud.org/results/@caddy/caddy/epel-8-x86_64/", pulp_type="file"
        )

    def tearDown(self):
        self.remote.delete()
        self.remote_without_credentials.delete()

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

    def test_accept_remote_without_credentials_but_with_at(self):
        apps_mock = Mock()
        apps_mock.get_model = Mock(return_value=Remote)

        # use import_module due to underscores
        migration = import_module("pulpcore.app.migrations.0077_move_remote_url_credentials")
        migration.move_remote_url_credentials(apps_mock, None)

        self.remote_without_credentials = Remote.objects.get(name="test-url-no-credentials")
        self.assertEqual(self.remote_without_credentials.url, "https://download.copr.fedorainfracloud.org/results/@caddy/caddy/epel-8-x86_64/")
