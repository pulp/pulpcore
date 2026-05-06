import pytest

from pulpcore.pytest_plugin import (
    KEY_V4_RSA4K_PRIVATE,
    create_signing_service,
    import_signing_key,
    make_signing_script,
    remove_signing_service,
)


@pytest.mark.parallel
def test_crud_signing_service(ascii_armored_detached_signing_service):
    service = ascii_armored_detached_signing_service
    assert "/api/v3/signing-services/" in service.pulp_href


def test_add_signing_service_key_with_subkeys(tmp_path_factory):
    """Verify that add-signing-service works with a PGP key that has subkeys.

    Keys with signing subkeys produce multiple fpr: lines in GPG's colon
    output, which previously caused add-signing-service to fail.
    """
    gpg_home = tmp_path_factory.mktemp("gpghome_subkey_test")
    _gpg, fingerprint, _keyid = import_signing_key(KEY_V4_RSA4K_PRIVATE, gpg_home)
    script_path = make_signing_script(gpg_home, fingerprint)
    service_name = create_signing_service(gpg_home, fingerprint, script_path)
    assert len(fingerprint) == 40

    remove_signing_service(service_name)
