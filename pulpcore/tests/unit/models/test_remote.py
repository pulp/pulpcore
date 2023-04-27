import pytest
from uuid import uuid4

from django.db import connection

from pulpcore.app.models import Remote
from pulpcore.app.models.fields import _fernet, EncryptedTextField


@pytest.fixture
def fake_fernet(tmp_path, settings):
    key_file = tmp_path / "db_symmetric_key"
    key_file.write_bytes(b"hPCIFQV/upbvPRsEpgS7W32XdFA2EQgXnMtyNAekebQ=")
    settings.DB_ENCRYPTION_KEY = str(key_file)
    _fernet.cache_clear()
    yield
    _fernet.cache_clear()


@pytest.mark.django_db
def test_encrypted_proxy_password(fake_fernet):
    remote = Remote.objects.create(name=uuid4(), proxy_password="test")
    assert Remote.objects.get(pk=remote.pk).proxy_password == "test"

    # check the database that proxy_password is encrypted
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT proxy_password FROM core_remote WHERE pulp_id = %s;", (str(remote.pulp_id),)
        )
        db_proxy_password = cursor.fetchone()[0]
    proxy_password = EncryptedTextField().from_db_value(db_proxy_password, None, connection)
    assert db_proxy_password != "test"
    assert proxy_password == "test"
