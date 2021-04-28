from uuid import uuid4
from unittest.mock import patch, mock_open

from django.db import connection
from django.test import TestCase

from pulpcore.app.models import Remote
from pulpcore.app.models.fields import EncryptedTextField


class RemoteTestCase(TestCase):
    def setUp(self):
        self.remote = None

    def tearDown(self):
        if self.remote:
            self.remote.delete()

    @patch(
        "pulpcore.app.models.fields.open",
        new_callable=mock_open,
        read_data=b"hPCIFQV/upbvPRsEpgS7W32XdFA2EQgXnMtyNAekebQ=",
    )
    def test_encrypted_proxy_password(self, mock_file):
        self.remote = Remote(name=uuid4(), proxy_password="test")
        self.remote.save()
        self.assertEqual(Remote.objects.get(pk=self.remote.pk).proxy_password, "test")

        # check the database that proxy_password is encrypted
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT proxy_password FROM core_remote " f"WHERE pulp_id = '{self.remote.pulp_id}'"
            )
            db_proxy_password = cursor.fetchone()[0]
            proxy_password = EncryptedTextField().from_db_value(db_proxy_password, None, connection)
            self.assertNotEqual(db_proxy_password, "test")
            self.assertEqual(proxy_password, "test")
            self.assertEqual(mock_file.call_count, 2)
