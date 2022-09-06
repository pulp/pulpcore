import pytest


@pytest.mark.parallel
def test_crud_signing_service(ascii_armored_detached_signing_service):
    service = ascii_armored_detached_signing_service
    assert "/api/v3/signing-services/" in service.pulp_href
