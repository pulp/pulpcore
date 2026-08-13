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

#: KI-22/KI-27: `rotate-db-key` (management/commands/rotate-db-key.py) unconditionally loops
#: over every alias in `settings.DATABASES`, not just `default` -- see
#: `test_multi_database_routing.py`'s module docstring for why a real second alias must be
#: configured via `PULP_DATABASES__data_1__*` env vars for the satellite-hosted half of
#: `test_rotate_db_key` below to actually exercise anything.
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
    """KI-22/KI-27: `rotate-db-key` must re-encrypt encrypted fields on *every* configured
    database alias, not just `default`.

    The `databases=list(settings.DATABASES)` marker (rather than a hardcoded list, or the bare
    `@pytest.mark.django_db` this test used before) is what makes this test pass in both
    configurations described in the KI-27 writeup: with only `default` configured (today's CI,
    where `rotate-db-key`'s per-alias loop only ever has one alias to iterate and this is exactly
    the original test), and with a real `data_1` alias configured (`PULP_DATABASES__data_1__*`
    env vars -- see `test_multi_database_routing.py`'s module docstring), where the command's
    per-alias loop (`management/commands/rotate-db-key.py`) actually touches a second
    connection and a hardcoded `@pytest.mark.django_db` (declaring only `default`) would make
    pytest-django raise `DatabaseOperationForbidden` the moment the command reaches `data_1`.
    """
    remote = Remote.objects.create(name=uuid4(), proxy_password="test")
    domain = Domain.objects.create(name=uuid4(), storage_settings={"base_path": "/foo"})

    satellite_remote = None
    satellite_domain = None
    if SATELLITE_ALIAS in settings.DATABASES:
        # Prove KI-22 is actually fixed, not just that the command doesn't crash: create a
        # satellite-hosted encrypted-field object (routed to `data_1` via the domain's
        # `database_alias`, exactly like production data on a moved domain would be), and later
        # assert *that* object's ciphertext was rewritten with the new key too.
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
            # The satellite copy was actually re-encrypted with the new key (not left with the
            # old key's ciphertext, and not silently skipped) -- it now fails to decrypt with
            # the *old* key too, exactly like the `default`-hosted `remote` above. Use an
            # explicit `.using(SATELLITE_ALIAS)` fetch (rather than `del` + implicit
            # `refresh_from_db()`, as used for `remote` above): `satellite_remote` was created
            # outside of any `with_domain()` context by this point, so there's no ContextVar to
            # inform routing, and its `pulp_domain` relation was never fetched/cached either
            # (only `pulp_domain_id`, via the `default=get_domain_pk` callable) -- exactly the
            # scenario the router's instance-hint path intentionally no longer guesses at
            # post-KI-27, to avoid the N+1 bug. `from_db_value` decrypts eagerly during the
            # fetch itself, so the raise happens inside `.get()`, not on attribute access.
            with pytest.raises(InvalidToken):
                Remote.objects.using(SATELLITE_ALIAS).get(pk=satellite_remote.pk)
    finally:
        if satellite_remote is not None or satellite_domain is not None:
            # Deleting these rows requires Django's collector to SELECT them first (for
            # signals/cascades), which decrypts every encrypted field on the row regardless of
            # whether the test cares about its value -- restore a key file with every key used
            # above so that read succeeds no matter which rotation step we stopped at.
            key_file = Path(settings.DB_ENCRYPTION_KEY)
            key_file.write_bytes(TEST_KEY2 + b"\n" + TEST_KEY1)
            _fernet.cache_clear()
        if satellite_remote is not None:
            Remote.objects.using(SATELLITE_ALIAS).filter(pk=satellite_remote.pk).delete()
        if satellite_domain is not None:
            satellite_domain.delete()
