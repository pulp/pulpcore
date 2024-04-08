"""Constants for Pulp certguard plugin tests."""

import os


_CURRENT_DIR = os.path.dirname(os.path.realpath(__file__))


X509_BASE_PATH = "my-content-view"
X509_CERTS_BASE_PATH = os.path.join(_CURRENT_DIR, "artifacts", "x509", "certificates")
X509_CA_CERT_FILE_PATH = os.path.join(X509_CERTS_BASE_PATH, "ca.pem")
X509_CLIENT_CERT_FILE_PATH = os.path.join(X509_CERTS_BASE_PATH, "client.pem")
X509_UNTRUSTED_CLIENT_CERT_FILE_PATH = os.path.join(X509_CERTS_BASE_PATH, "untrusted_client.pem")
X509_UN_URLENCODED_CLIENT_CERT_FILE_PATH = os.path.join(
    X509_CERTS_BASE_PATH, "un_urlencoded_cert.txt"
)


RHSM_CA_CERT_FILE_PATH = os.path.join(_CURRENT_DIR, "artifacts", "rhsm", "katello-default-ca.crt")

RHSM_CLIENT_CERT_FROM_UNTRUSTED_CA = os.path.join(
    _CURRENT_DIR, "artifacts", "rhsm", "untrusted_cert.pem"
)

RHSM_CLIENT_CERT_TRUSTED_BUT_EXPIRED = os.path.join(
    _CURRENT_DIR, "artifacts", "rhsm", "trusted_but_expired.pem"
)

THIRDPARTY_CA_CERT_FILE_PATH = os.path.join(
    _CURRENT_DIR, "artifacts", "thirdparty_ca", "certificates", "ca.pem"
)


# Uber cert path: /Default_Organization
RHSM_UBER_CLIENT_CERT = os.path.join(_CURRENT_DIR, "artifacts", "rhsm", "uber.cert")
RHSM_UBER_CERT_BASE_PATH_ONE = "Default_Organization/my-content-view"
RHSM_UBER_CERT_BASE_PATH_TWO = "Default_Organization/another-content-view"


# Zero_var path: /Default_Organization/Library/custom/foo/foo
RHSM_V1_ZERO_VAR_CLIENT_CERT = os.path.join(
    _CURRENT_DIR, "artifacts", "rhsm", "v1", "159442575569388840.pem"
)
RHSM_V1_ZERO_VAR_BASE_PATH = "Default_Organization/Library/custom/foo/foo"


# One var path: /Default_Organization/Library/content/dist/rhel/server/7/7Server/$basearch/extras/os
# Two var path: /Default_Organization/Library/content/dist/rhel/server/7/$releasever/$basearch/os
RHSM_V1_ONE_AND_TWO_VAR_CLIENT_CERT = os.path.join(
    _CURRENT_DIR, "artifacts", "rhsm", "v1", "1514454871848760713.pem"
)
RHSM_V1_ONE_VAR_BASE_PATH = (
    "Default_Organization/Library/content/dist/rhel/server/7/7Server/x86_64/extras/os"
)
RHSM_V1_TWO_VAR_BASE_PATH = "Default_Organization/Library/content/dist/rhel/server/7/7.4/x86_64/os"


# Zero_var path: /Default_Organization/Library/custom/foo/foo
RHSM_V3_ZERO_VAR_CLIENT_CERT = os.path.join(
    _CURRENT_DIR, "artifacts", "rhsm", "v3", "4260035510644027985.pem"
)
RHSM_V3_ZERO_VAR_BASE_PATH = "Default_Organization/Library/custom/foo/foo"
RHSM_V3_INVALID_BASE_PATH = "this-is-not-a-valid-base-path"


# One var path: /Default_Organization/Library/content/dist/rhel8/$releasever/x86_64/baseos/os
# Two var path: /Default_Organization/Library/content/dist/rhel/server/7/$releasever/$basearch/os
RHSM_V3_ONE_AND_TWO_VAR_CLIENT_CERT = os.path.join(
    _CURRENT_DIR, "artifacts", "rhsm", "v3", "5527980418107729172.pem"
)
RHSM_V3_ONE_VAR_BASE_PATH = "Default_Organization/Library/content/dist/rhel8/8/x86_64/baseos/os"
RHSM_V3_TWO_VAR_BASE_PATH = "Default_Organization/Library/content/dist/rhel/server/7/7.4/x86_64/os"
