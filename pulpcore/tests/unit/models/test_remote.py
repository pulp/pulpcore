from pathlib import Path
from uuid import uuid4

import pytest
from cryptography.fernet import InvalidToken
from django.conf import settings
from django.core.management import call_command
from django.db import connection

from pulpcore.app.contexts import with_domain
from pulpcore.app.models import Domain, Remote
from pulpcore.app.models.fields import EncryptedTextField, _fernet

TEST_KEY1 = b"hPCIFQV/upbvPRsEpgS7W32XdFA2EQgXnMtyNAekebQ="
TEST_KEY2 = b"6Xyv+QezAQ+4R870F5qsgKcngzmm46caDB2gyo9qnpc="

SATELLITE_ALIAS = "data_1"


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


@pytest.mark.django_db(databases=list(settings.DATABASES))
def test_rotate_db_key(fake_fernet):
    remote = Remote.objects.create(name=uuid4(), proxy_password="test")
    domain = Domain.objects.create(name=uuid4(), storage_settings={"base_path": "/foo"})

    satellite_remote = None
    satellite_domain = None
    if SATELLITE_ALIAS in settings.DATABASES:
        satellite_domain = Domain.objects.create(
            name=uuid4(),
            storage_class="pulpcore.app.models.storage.FileSystem",
            storage_settings={"base_path": "/satellite"},
            database_alias=SATELLITE_ALIAS,
        )
        with with_domain(satellite_domain):
            satellite_remote = Remote.objects.create(
                name=uuid4(), proxy_password="satellite-secret"
            )
        assert not Remote.objects.using("default").filter(pk=satellite_remote.pk).exists()
        assert Remote.objects.using(SATELLITE_ALIAS).filter(pk=satellite_remote.pk).exists()

    try:
        next(fake_fernet)  # new + old key

        call_command("rotate-db-key")

        next(fake_fernet)  # new key

        del remote.proxy_password
        assert remote.proxy_password == "test"
        del domain.storage_settings
        assert domain.storage_settings == {"base_path": "/foo"}

        if satellite_remote is not None:
            satellite_remote = Remote.objects.using(SATELLITE_ALIAS).get(pk=satellite_remote.pk)
            assert satellite_remote.proxy_password == "satellite-secret"

        next(fake_fernet)  # old key

        del remote.proxy_password
        with pytest.raises(InvalidToken):
            remote.proxy_password
        del domain.storage_settings
        with pytest.raises(InvalidToken):
            domain.storage_settings

        if satellite_remote is not None:
            with pytest.raises(InvalidToken):
                Remote.objects.using(SATELLITE_ALIAS).get(pk=satellite_remote.pk)
    finally:
        if satellite_remote is not None or satellite_domain is not None:
            key_file = Path(settings.DB_ENCRYPTION_KEY)
            key_file.write_bytes(TEST_KEY2 + b"\n" + TEST_KEY1)
            _fernet.cache_clear()
        if satellite_remote is not None:
            Remote.objects.using(SATELLITE_ALIAS).filter(pk=satellite_remote.pk).delete()
        if satellite_domain is not None:
            satellite_domain.delete()
