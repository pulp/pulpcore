import json
import subprocess
import uuid

import requests
import gnupg
import pytest


SIGNING_SCRIPT_STRING = r"""#!/usr/bin/env bash

FILE_PATH=$1
SIGNATURE_PATH="$1.asc"

GPG_KEY_ID="pulp-fixture-signing-key"

# Create a detached signature
gpg --quiet --batch --homedir HOMEDIRHERE --detach-sign --local-user "${GPG_KEY_ID}" \
   --armor --output ${SIGNATURE_PATH} ${FILE_PATH}

# Check the exit status
STATUS=$?
if [[ ${STATUS} -eq 0 ]]; then
   echo {\"file\": \"${FILE_PATH}\", \"signature\": \"${SIGNATURE_PATH}\"}
else
   exit ${STATUS}
fi
"""


@pytest.fixture(scope="session")
def signing_script_path(signing_script_temp_dir, signing_gpg_homedir_path):
    signing_script_file = signing_script_temp_dir / "sign-metadata.sh"
    signing_script_file.write_text(
        SIGNING_SCRIPT_STRING.replace("HOMEDIRHERE", str(signing_gpg_homedir_path))
    )

    signing_script_file.chmod(0o755)

    return signing_script_file


@pytest.fixture(scope="session")
def signing_script_temp_dir(tmp_path_factory):
    return tmp_path_factory.mktemp("sigining_script_dir")


@pytest.fixture(scope="session")
def signing_gpg_homedir_path(tmp_path_factory):
    return tmp_path_factory.mktemp("gpghome")


@pytest.fixture
def sign_with_ascii_armored_detached_signing_service(signing_script_path, signing_gpg_metadata):
    """
    Runs the test signing script manually, locally, and returns the signature file produced.
    """

    def _sign_with_ascii_armored_detached_signing_service(filename):
        env = {"PULP_SIGNING_KEY_FINGERPRINT": signing_gpg_metadata[1]}
        cmd = (signing_script_path, filename)
        completed_process = subprocess.run(
            cmd,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        if completed_process.returncode != 0:
            raise RuntimeError(str(completed_process.stderr))

        try:
            return_value = json.loads(completed_process.stdout)
        except json.JSONDecodeError:
            raise RuntimeError("The signing script did not return valid JSON!")

        return return_value

    return _sign_with_ascii_armored_detached_signing_service


@pytest.fixture(scope="session")
def signing_gpg_metadata(signing_gpg_homedir_path):
    """A fixture that returns a GPG instance and related metadata (i.e., fingerprint, keyid)."""
    PRIVATE_KEY_URL = "https://raw.githubusercontent.com/pulp/pulp-fixtures/master/common/GPG-PRIVATE-KEY-fixture-signing"  # noqa: E501

    response = requests.get(PRIVATE_KEY_URL)
    response.raise_for_status()

    gpg = gnupg.GPG(gnupghome=signing_gpg_homedir_path)
    gpg.import_keys(response.content)

    fingerprint = gpg.list_keys()[0]["fingerprint"]
    keyid = gpg.list_keys()[0]["keyid"]

    gpg.trust_keys(fingerprint, "TRUST_ULTIMATE")

    return gpg, fingerprint, keyid


@pytest.fixture(scope="session")
def pulp_trusted_public_key(signing_gpg_metadata):
    """Fixture to extract the ascii armored trusted public test key."""
    gpg, _, keyid = signing_gpg_metadata
    return gpg.export_keys([keyid])


@pytest.fixture(scope="session")
def pulp_trusted_public_key_fingerprint(signing_gpg_metadata):
    """Fixture to extract the ascii armored trusted public test keys fingerprint."""
    return signing_gpg_metadata[1]


@pytest.fixture(scope="session")
def _ascii_armored_detached_signing_service_name(
    bindings_cfg,
    signing_script_path,
    signing_gpg_metadata,
    signing_gpg_homedir_path,
    pytestconfig,
):
    service_name = str(uuid.uuid4())
    gpg, fingerprint, keyid = signing_gpg_metadata

    cmd = (
        "pulpcore-manager",
        "add-signing-service",
        service_name,
        str(signing_script_path),
        fingerprint,
        "--class",
        "core:AsciiArmoredDetachedSigningService",
        "--gnupghome",
        str(signing_gpg_homedir_path),
    )
    completed_process = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    assert completed_process.returncode == 0

    yield service_name

    cmd = (
        "pulpcore-manager",
        "remove-signing-service",
        service_name,
        "--class",
        "core:AsciiArmoredDetachedSigningService",
    )
    subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


@pytest.fixture
def ascii_armored_detached_signing_service(
    _ascii_armored_detached_signing_service_name, signing_service_api_client
):
    return signing_service_api_client.list(
        name=_ascii_armored_detached_signing_service_name
    ).results[0]
