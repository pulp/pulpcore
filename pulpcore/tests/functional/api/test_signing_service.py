import pytest

from pulpcore.pytest_plugin import (
    KEY_V4_RSA4K_PRIVATE,
    create_signing_service,
    import_signing_key,
    make_signing_script,
    remove_signing_service,
)


@pytest.mark.parallel
@pytest.mark.parametrize(
    "signing_service_fixture",
    [
        "ascii_armored_detached_signing_service",
        "sq_ascii_armored_detached_signing_service",
    ],
)
def test_crud_signing_service(signing_service_fixture, request):
    service = request.getfixturevalue(signing_service_fixture)
    assert "/api/v3/signing-services/" in service.pulp_href


@pytest.mark.parametrize("backend", ["gpg", "sq"])
def test_add_signing_service_key_with_subkeys(backend, tmp_path_factory):
    """Verify that add-signing-service works with a PGP key that has subkeys.

    Keys with signing subkeys produce multiple fpr: lines in GPG's colon
    output, which previously caused add-signing-service to fail.

    With both GPG and Sequoia backends, the service should be created
    successfully with the primary key fingerprint.
    """
    home = tmp_path_factory.mktemp(f"{backend}_subkey_test")
    script_dir = tmp_path_factory.mktemp(f"{backend}_subkey_script")
    _gpg, fingerprint, _keyid = import_signing_key(KEY_V4_RSA4K_PRIVATE, home, backend=backend)
    script_path = make_signing_script(home, fingerprint, script_dir, backend=backend)
    service_name = create_signing_service(home, fingerprint, script_path, backend=backend)

    assert len(fingerprint) in (40, 64)

    remove_signing_service(service_name)
