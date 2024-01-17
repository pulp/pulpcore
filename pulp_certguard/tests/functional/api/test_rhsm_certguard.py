import pytest
import uuid

import requests
from urllib.parse import urljoin, quote
from django.conf import settings

from pulp_certguard.tests.functional.constants import (
    RHSM_CA_CERT_FILE_PATH,
    RHSM_CLIENT_CERT_FROM_UNTRUSTED_CA,
    RHSM_CLIENT_CERT_TRUSTED_BUT_EXPIRED,
    THIRDPARTY_CA_CERT_FILE_PATH,
    RHSM_UBER_CERT_BASE_PATH_ONE,
    RHSM_UBER_CERT_BASE_PATH_TWO,
    RHSM_UBER_CLIENT_CERT,
    RHSM_V1_ONE_AND_TWO_VAR_CLIENT_CERT,
    RHSM_V1_ONE_VAR_BASE_PATH,
    RHSM_V1_TWO_VAR_BASE_PATH,
    RHSM_V1_ZERO_VAR_CLIENT_CERT,
    RHSM_V1_ZERO_VAR_BASE_PATH,
    RHSM_V3_INVALID_BASE_PATH,
    RHSM_V3_ONE_AND_TWO_VAR_CLIENT_CERT,
    RHSM_V3_ONE_VAR_BASE_PATH,
    RHSM_V3_TWO_VAR_BASE_PATH,
    RHSM_V3_ZERO_VAR_CLIENT_CERT,
    RHSM_V3_ZERO_VAR_BASE_PATH,
)


if settings.DOMAIN_ENABLED:
    pytest.skip("RHSM tests are currently not compatible with domains.", allow_module_level=True)


@pytest.fixture(scope="class")
def rhsm_certguard_factory(rhsm_content_guards_api_client, gen_object_with_cleanup):
    def _rhsm_certguard_factory(thirdparty=False, **body):
        with open(RHSM_CA_CERT_FILE_PATH, "r") as rhsm_ca_cert_data_file:
            ca_cert_data = rhsm_ca_cert_data_file.read()
        if thirdparty:
            with open(THIRDPARTY_CA_CERT_FILE_PATH, "r") as thirdparty_ca_cert_file:
                ca_cert_data = thirdparty_ca_cert_file.read() + ca_cert_data

        body.setdefault("name", str(uuid.uuid4()))
        body.setdefault("ca_certificate", ca_cert_data)
        return gen_object_with_cleanup(rhsm_content_guards_api_client, body)

    return _rhsm_certguard_factory


@pytest.fixture(scope="class")
def rhsm_certguard(rhsm_certguard_factory):
    return rhsm_certguard_factory()


@pytest.fixture(scope="class")
def rhsm_guarded_distribution_v3_zero(
    rhsm_certguard,
    file_distribution_factory,
    repository_test_file,
):
    distribution = file_distribution_factory(
        base_path=RHSM_V3_ZERO_VAR_BASE_PATH,
        repository=repository_test_file.pulp_href,
        content_guard=rhsm_certguard.pulp_href,
    )
    return distribution


@pytest.fixture(scope="class")
def rhsm_guarded_distribution_v3_one(
    rhsm_certguard,
    file_distribution_factory,
    repository_test_file,
):
    distribution = file_distribution_factory(
        base_path=RHSM_V3_ONE_VAR_BASE_PATH,
        repository=repository_test_file.pulp_href,
        content_guard=rhsm_certguard.pulp_href,
    )
    return distribution


@pytest.fixture(scope="class")
def rhsm_guarded_distribution_v3_two(
    rhsm_certguard,
    file_distribution_factory,
    repository_test_file,
):
    distribution = file_distribution_factory(
        base_path=RHSM_V3_TWO_VAR_BASE_PATH,
        repository=repository_test_file.pulp_href,
        content_guard=rhsm_certguard.pulp_href,
    )
    return distribution


@pytest.fixture(scope="class")
def rhsm_guarded_distribution_v3_invalid(
    rhsm_certguard,
    file_distribution_factory,
    repository_test_file,
):
    distribution = file_distribution_factory(
        base_path=RHSM_V3_INVALID_BASE_PATH,
        repository=repository_test_file.pulp_href,
        content_guard=rhsm_certguard.pulp_href,
    )
    return distribution


@pytest.fixture(scope="class")
def rhsm_guarded_distribution_v1_zero(
    rhsm_certguard,
    file_distribution_factory,
    repository_test_file,
):
    distribution = file_distribution_factory(
        base_path=RHSM_V1_ZERO_VAR_BASE_PATH,
        repository=repository_test_file.pulp_href,
        content_guard=rhsm_certguard.pulp_href,
    )
    return distribution


@pytest.fixture(scope="class")
def rhsm_guarded_distribution_v1_one(
    rhsm_certguard,
    file_distribution_factory,
    repository_test_file,
):
    distribution = file_distribution_factory(
        base_path=RHSM_V1_ONE_VAR_BASE_PATH,
        repository=repository_test_file.pulp_href,
        content_guard=rhsm_certguard.pulp_href,
    )
    return distribution


@pytest.fixture(scope="class")
def rhsm_guarded_distribution_v1_two(
    rhsm_certguard,
    file_distribution_factory,
    repository_test_file,
):
    distribution = file_distribution_factory(
        base_path=RHSM_V1_TWO_VAR_BASE_PATH,
        repository=repository_test_file.pulp_href,
        content_guard=rhsm_certguard.pulp_href,
    )
    return distribution


@pytest.fixture(scope="class")
def rhsm_guarded_distribution_uber_one(
    rhsm_certguard,
    file_distribution_factory,
    repository_test_file,
):
    distribution = file_distribution_factory(
        base_path=RHSM_UBER_CERT_BASE_PATH_ONE,
        repository=repository_test_file.pulp_href,
        content_guard=rhsm_certguard.pulp_href,
    )
    return distribution


@pytest.fixture(scope="class")
def rhsm_guarded_distribution_uber_two(
    rhsm_certguard,
    file_distribution_factory,
    repository_test_file,
):
    distribution = file_distribution_factory(
        base_path=RHSM_UBER_CERT_BASE_PATH_TWO,
        repository=repository_test_file.pulp_href,
        content_guard=rhsm_certguard.pulp_href,
    )
    return distribution


@pytest.fixture(scope="class")
def rhsmca_guarded_distribution(
    rhsm_certguard_factory,
    file_distribution_factory,
    repository_test_file,
):
    """A distribution serving a single file at "test_file" guarded by an rhsm content guard."""
    content_guard = rhsm_certguard_factory(thirdparty=True)
    distribution = file_distribution_factory(
        base_path=RHSM_V3_ZERO_VAR_BASE_PATH,
        repository=repository_test_file.pulp_href,
        content_guard=content_guard.pulp_href,
    )
    return distribution


class TestRHSMCertGuard:
    """Api tests for RHSMCertGard with RHSM Certificates."""

    def test_allow_request_when_cert_matches_zero_var_path(
        self, rhsm_guarded_distribution_v3_zero, content_path
    ):
        """
        Assert a correctly configured client can fetch content from a zero-variable path.

        1. Configure the distribution with a zero-variable path in the RHSM Cert.
        2. Attempt to download content.
        """

        with open(RHSM_V3_ZERO_VAR_CLIENT_CERT, "r") as cert_file:
            cert_data = quote(cert_file.read())
        response = requests.get(
            urljoin(rhsm_guarded_distribution_v3_zero.base_url, content_path),
            headers={"X-CLIENT-CERT": cert_data},
        )
        assert response.status_code == 200

    def test_allow_request_when_cert_matches_one_var_path(
        self, rhsm_guarded_distribution_v3_one, content_path
    ):
        """
        Assert a correctly configured client can fetch content from a one-variable path.

        1. Configure the distribution with a one-variable path in the RHSM Cert.
        2. Attempt to download content.
        """
        with open(RHSM_V3_ONE_AND_TWO_VAR_CLIENT_CERT, "r") as cert_file:
            cert_data = quote(cert_file.read())
        response = requests.get(
            urljoin(rhsm_guarded_distribution_v3_one.base_url, content_path),
            headers={"X-CLIENT-CERT": cert_data},
        )
        assert response.status_code == 200

    def test_allow_request_when_cert_matches_two_var_path(
        self, rhsm_guarded_distribution_v3_two, content_path
    ):
        """
        Assert a correctly configured client can fetch content from a two-variable path.

        1. Configure the distribution with a two-variable path in the RHSM Cert.
        2. Attempt to download content.
        """
        with open(RHSM_V3_ONE_AND_TWO_VAR_CLIENT_CERT, "r") as cert_file:
            cert_data = quote(cert_file.read())
        response = requests.get(
            urljoin(rhsm_guarded_distribution_v3_two.base_url, content_path),
            headers={"X-CLIENT-CERT": cert_data},
        )
        assert response.status_code == 200

    def test_allow_request_to_subdir_of_path(self, rhsm_guarded_distribution_v3_zero):
        """
        Assert a correctly configured client can fetch content from a subdir of a distribution.

        1. Configure the distribution with a zero-variable path in the RHSM Cert.
        2. Attempt to download a content url with a subdir in it.
        3. Assert a 404 was received.
        """
        content_path = "somedir/made_up_content.iso"

        with open(RHSM_V3_ZERO_VAR_CLIENT_CERT, "r") as cert_file:
            cert_data = quote(cert_file.read())
        response = requests.get(
            urljoin(rhsm_guarded_distribution_v3_zero.base_url, content_path),
            headers={"X-CLIENT-CERT": cert_data},
        )
        # The path doesn't exist so we expect a 404, but the authorization part we are testing works
        assert response.status_code == 404

    @pytest.mark.parametrize("cert_data", [None, "", "this is not cert data"])
    def test_deny_requests_with_bad_cert_data(
        self, cert_data, content_path, rhsm_guarded_distribution_v3_zero
    ):
        response = requests.get(
            urljoin(rhsm_guarded_distribution_v3_zero.base_url, content_path),
            headers=cert_data and {"X-CLIENT-CERT": cert_data},
        )
        assert response.status_code == 403

    def test_deny_when_client_cert_does_not_contain_subpath_of_distribution_base_path(
        self, rhsm_guarded_distribution_v3_invalid, content_path
    ):
        with open(RHSM_V3_ZERO_VAR_CLIENT_CERT, "r") as cert_file:
            cert_data = quote(cert_file.read())
        response = requests.get(
            urljoin(rhsm_guarded_distribution_v3_invalid.base_url, content_path),
            headers=cert_data and {"X-CLIENT-CERT": cert_data},
        )
        assert response.status_code == 403

    def test_deny_when_client_cert_is_trusted_but_expired(
        self, rhsm_guarded_distribution_v3_one, content_path
    ):
        with open(RHSM_CLIENT_CERT_TRUSTED_BUT_EXPIRED, "r") as cert_file:
            cert_data = quote(cert_file.read())
        response = requests.get(
            urljoin(rhsm_guarded_distribution_v3_one.base_url, content_path),
            headers=cert_data and {"X-CLIENT-CERT": cert_data},
        )
        assert response.status_code == 403

    def test_deny_when_client_cert_is_untrusted(
        self, rhsm_guarded_distribution_v3_one, content_path
    ):
        with open(RHSM_CLIENT_CERT_FROM_UNTRUSTED_CA, "r") as cert_file:
            cert_data = quote(cert_file.read())
        response = requests.get(
            urljoin(rhsm_guarded_distribution_v3_one.base_url, content_path),
            headers=cert_data and {"X-CLIENT-CERT": cert_data},
        )
        assert response.status_code == 403

    def test_allow_request_with_uber_cert_for_any_subpath(
        self, rhsm_guarded_distribution_uber_one, rhsm_guarded_distribution_uber_two, content_path
    ):
        with open(RHSM_UBER_CLIENT_CERT, "r") as cert_file:
            cert_data = quote(cert_file.read())
        response = requests.get(
            urljoin(rhsm_guarded_distribution_uber_one.base_url, content_path),
            headers=cert_data and {"X-CLIENT-CERT": cert_data},
        )
        assert response.status_code == 200
        response = requests.get(
            urljoin(rhsm_guarded_distribution_uber_two.base_url, content_path),
            headers=cert_data and {"X-CLIENT-CERT": cert_data},
        )
        assert response.status_code == 200


class TestRHSMV1CertGuard:
    def test_v1_allow_request_when_cert_matches_zero_var_path(
        self, rhsm_guarded_distribution_v1_zero, content_path
    ):
        """
        Assert a correctly configured client can fetch content from a zero-variable path.

        1. Configure the distribution with a zero-variable path in the RHSM Cert.
        2. Attempt to download content.
        """
        with open(RHSM_V1_ZERO_VAR_CLIENT_CERT, "r") as cert_file:
            cert_data = quote(cert_file.read())
        response = requests.get(
            urljoin(rhsm_guarded_distribution_v1_zero.base_url, content_path),
            headers=cert_data and {"X-CLIENT-CERT": cert_data},
        )
        assert response.status_code == 200

    def test_v1_allow_request_when_cert_matches_one_var_path(
        self, rhsm_guarded_distribution_v1_one, content_path
    ):
        """
        Assert a correctly configured client can fetch content from a one-variable path.

        1. Configure the distribution with a one-variable path in the RHSM Cert.
        2. Attempt to download content.
        """
        with open(RHSM_V1_ONE_AND_TWO_VAR_CLIENT_CERT, "r") as cert_file:
            cert_data = quote(cert_file.read())
        response = requests.get(
            urljoin(rhsm_guarded_distribution_v1_one.base_url, content_path),
            headers=cert_data and {"X-CLIENT-CERT": cert_data},
        )
        assert response.status_code == 200

    def test_v1_allow_request_when_cert_matches_two_var_path(
        self, rhsm_guarded_distribution_v1_two, content_path
    ):
        """
        Assert a correctly configured client can fetch content from a two-variable path.

        1. Configure the distribution with a two-variable path in the RHSM Cert.
        2. Attempt to download content.
        """
        with open(RHSM_V1_ONE_AND_TWO_VAR_CLIENT_CERT, "r") as cert_file:
            cert_data = quote(cert_file.read())
        response = requests.get(
            urljoin(rhsm_guarded_distribution_v1_two.base_url, content_path),
            headers=cert_data and {"X-CLIENT-CERT": cert_data},
        )
        assert response.status_code == 200

    def test_v1_allow_request_to_subdir_of_path(self, rhsm_guarded_distribution_v1_zero):
        """
        Assert a correctly configured client can fetch content from a subdir of a distribution.

        1. Configure the distribution with a zero-variable path in the RHSM Cert.
        2. Attempt to download a content url with a subdir in it.
        3. Assert a 404 was received.
        """
        content_path = "somedir/made_up_content.iso"
        with open(RHSM_V1_ZERO_VAR_CLIENT_CERT, "r") as cert_file:
            cert_data = quote(cert_file.read())
        response = requests.get(
            urljoin(rhsm_guarded_distribution_v1_zero.base_url, content_path),
            headers=cert_data and {"X-CLIENT-CERT": cert_data},
        )
        # The path doesn't exist so we expect a 404, but the authorization part we are testing works
        assert response.status_code == 404


class TestRHSMCACertGuard:
    """Api tests for RHSMCertGard with RHSM Certificate bundles."""

    # Extra class because base_path collides.
    def test_allow_request_with_ca_bundle(self, rhsmca_guarded_distribution, content_path):
        with open(RHSM_V3_ZERO_VAR_CLIENT_CERT, "r") as cert_file:
            cert_data = quote(cert_file.read())
        response = requests.get(
            urljoin(rhsmca_guarded_distribution.base_url, content_path),
            headers=cert_data and {"X-CLIENT-CERT": cert_data},
        )
        assert response.status_code == 200
