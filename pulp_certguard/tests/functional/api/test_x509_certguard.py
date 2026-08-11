import uuid
from collections import namedtuple
from urllib.parse import quote, urljoin

import pytest
import requests

from pulp_certguard.tests.functional.constants import (
    X509_BASE_PATH,
    X509_CA_CERT_FILE_PATH,
    X509_CLIENT_CERT_FILE_PATH,
    X509_UN_URLENCODED_CLIENT_CERT_FILE_PATH,
    X509_UNTRUSTED_CLIENT_CERT_FILE_PATH,
)

PQCGuardedDistribution = namedtuple(
    "PQCGuardedDistribution",
    ["distribution", "algorithm", "client_cert_pem", "untrusted_client_cert_pem"],
)


@pytest.fixture(scope="class")
def x509_certguard_factory(x509_content_guards_api_client, gen_object_with_cleanup):
    def _x509_certguard_factory(**body):
        with open(X509_CA_CERT_FILE_PATH, "r") as x509_ca_cert_data_file:
            ca_cert_data = x509_ca_cert_data_file.read()

        body.setdefault("name", str(uuid.uuid4()))
        body.setdefault("ca_certificate", ca_cert_data)
        return gen_object_with_cleanup(x509_content_guards_api_client, body)

    return _x509_certguard_factory


@pytest.fixture(scope="class")
def x509_guarded_distribution(
    x509_certguard_factory,
    file_distribution_factory,
    repository_test_file,
):
    """A distribution serving a single file at "test_file" guarded by an x509 content guard."""
    content_guard = x509_certguard_factory()
    distribution = file_distribution_factory(
        base_path=X509_BASE_PATH,
        repository=repository_test_file.pulp_href,
        content_guard=content_guard.pulp_href,
    )
    return distribution


@pytest.fixture(scope="class")
def pqc_guarded_distribution(
    pqc_certificate_authority,
    x509_content_guards_api_client,
    gen_object_with_cleanup,
    file_distribution_factory,
    repository_test_file,
):
    pca = pqc_certificate_authority
    content_guard = gen_object_with_cleanup(
        x509_content_guards_api_client,
        {
            "name": str(uuid.uuid4()),
            "ca_certificate": pca.ca_cert_pem,
        },
    )
    distribution = file_distribution_factory(
        repository=repository_test_file.pulp_href,
        content_guard=content_guard.pulp_href,
    )
    return PQCGuardedDistribution(
        distribution, pca.algorithm, pca.client_cert_pem, pca.untrusted_client_cert_pem
    )


@pytest.fixture(
    scope="module",
    params=[
        "good cert",
        "un_urlencoded cert",
        "untrusted cert",
        "no cert",
        "empty cert",
        "invalid cert data",
    ],
)
def parameterized_cert(request):
    """A tuple of the cert and the expected http status code."""
    if request.param == "good cert":
        with open(X509_CLIENT_CERT_FILE_PATH, "r") as cert_file:
            return quote(cert_file.read()), 200
    elif request.param == "un_urlencoded cert":
        with open(X509_UN_URLENCODED_CLIENT_CERT_FILE_PATH, "r") as cert_file:
            return cert_file.read(), 200
    elif request.param == "untrusted cert":
        with open(X509_UNTRUSTED_CLIENT_CERT_FILE_PATH, "r") as cert_file:
            return quote(cert_file.read()), 403
    elif request.param == "no cert":
        return None, 403
    elif request.param == "empty cert":
        return "", 403
    elif request.param == "invalid cert data":
        return "this is not cert data", 403
    else:
        raise NotImplementedError(request.param)


class TestX509CertGuard:
    """A test class to share the costly distribution setup."""

    def test_download(
        self,
        x509_guarded_distribution,
        parameterized_cert,
        content_path,
        distribution_base_url,
    ):
        cert_data, status_code = parameterized_cert

        distribution_base_url = distribution_base_url(x509_guarded_distribution.base_url)
        response = requests.get(
            urljoin(distribution_base_url, content_path),
            headers=cert_data and {"X-CLIENT-CERT": cert_data},
        )
        assert response.status_code == status_code


class TestPQCX509CertGuard:
    """Test X.509 content guard with PQC (ML-DSA) certificates.

    Parameterized over ML-DSA-65 (~7.5KB, under the default 8190-byte header
    limit) and ML-DSA-87 (~10KB, over the limit).
    """

    def test_download_with_valid_cert(
        self,
        pqc_guarded_distribution,
        distribution_base_url,
    ):
        distribution = pqc_guarded_distribution.distribution
        url = distribution_base_url(distribution.base_url)
        cert_pem = quote(pqc_guarded_distribution.client_cert_pem)
        response = requests.get(
            urljoin(url, "test_file"),
            headers={"X-CLIENT-CERT": cert_pem},
            allow_redirects=False,
        )
        assert response.status_code in (200, 302)

    def test_download_with_untrusted_cert(
        self,
        pqc_guarded_distribution,
        distribution_base_url,
    ):
        distribution = pqc_guarded_distribution.distribution
        url = distribution_base_url(distribution.base_url)
        cert_pem = quote(pqc_guarded_distribution.untrusted_client_cert_pem)
        response = requests.get(
            urljoin(url, "test_file"),
            headers={"X-CLIENT-CERT": cert_pem},
        )
        assert response.status_code == 403

    def test_download_with_no_cert(
        self,
        pqc_guarded_distribution,
        distribution_base_url,
    ):
        distribution = pqc_guarded_distribution.distribution
        url = distribution_base_url(distribution.base_url)
        response = requests.get(urljoin(url, "test_file"))
        assert response.status_code == 403
