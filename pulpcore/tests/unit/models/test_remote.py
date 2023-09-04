import pytest
from uuid import uuid4
from cryptography.fernet import InvalidToken

from django.core.management import call_command
from django.db import connection

from pulpcore.app.models import Remote, Domain
from pulpcore.app.models.fields import _fernet, EncryptedTextField


TEST_KEY1 = b"hPCIFQV/upbvPRsEpgS7W32XdFA2EQgXnMtyNAekebQ="
TEST_KEY2 = b"6Xyv+QezAQ+4R870F5qsgKcngzmm46caDB2gyo9qnpc="


@pytest.fixture
def fake_fernet(tmp_path, settings):
    def _steps():
        yield
        key_file.write_bytes(TEST_KEY2 + b"\n" + TEST_KEY1)
        _fernet.cache_clear()
        yield
        key_file.write_bytes(TEST_KEY2)
        _fernet.cache_clear()
        yield
        key_file.write_bytes(TEST_KEY1)
        _fernet.cache_clear()
        yield

    key_file = tmp_path / "db_symmetric_key"
    key_file.write_bytes(TEST_KEY1)
    settings.DB_ENCRYPTION_KEY = str(key_file)
    _fernet.cache_clear()
    yield _steps()
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


@pytest.mark.django_db
def test_rotate_db_key(fake_fernet):
    remote = Remote.objects.create(name=uuid4(), proxy_password="test")
    domain = Domain.objects.create(name=uuid4(), storage_settings={"base_path": "/foo"})

    next(fake_fernet)  # new + old key

    call_command("rotate-db-key")

    next(fake_fernet)  # new key

    del remote.proxy_password
    assert remote.proxy_password == "test"
    del domain.storage_settings
    assert domain.storage_settings == {"base_path": "/foo"}

    next(fake_fernet)  # old key

    del remote.proxy_password
    with pytest.raises(InvalidToken):
        remote.proxy_password
    del domain.storage_settings
    with pytest.raises(InvalidToken):
        domain.storage_settings
