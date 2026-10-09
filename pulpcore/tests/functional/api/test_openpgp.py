import re
import uuid

import pytest
import requests

from pulpcore.pytest_plugin import (
    KEY_V4_ED25519_PRIVATE,
    KEY_V4_ED25519_PUBLIC,
    KEY_V4_RSA2K_PUBLIC,
    KEY_V4_RSA4K_PUBLIC,
    KEY_V6_ED25519_PRIVATE,
    KEY_V6_ED25519_PUBLIC,
    KEY_V6_MLDSA65_ED25519_PUBLIC,
    KEY_V6_MLDSA87_ED448_PUBLIC,
    KEY_V6_RSA4K_PUBLIC,
)
from pulpcore.tests.functional.utils import PulpTaskError


def _download_key(url):
    response = requests.get(url)
    response.raise_for_status()
    return response.content


def _upload_key(tmpdir, pulpcore_bindings, monitor_task, key_data, keyring):
    key_path = tmpdir / f"{uuid.uuid4()}.asc"
    if isinstance(key_data, str):
        key_path.write_text(key_data, "UTF-8")
    else:
        key_path.write_binary(key_data)
    result = pulpcore_bindings.ContentOpenpgpPublickeyApi.create(
        file=str(key_path), repository=keyring.pulp_href
    )
    monitor_task(result.task)
    keyring = pulpcore_bindings.RepositoriesOpenpgpKeyringApi.read(keyring.pulp_href)
    return keyring


def _upload_key_from_url(tmpdir, pulpcore_bindings, monitor_task, url, keyring):
    key_data = _download_key(url)
    return _upload_key(tmpdir, pulpcore_bindings, monitor_task, key_data, keyring)


# ── Sample keys from IETF OpenPGP samples draft ──────────────────────────

ALICE_PUB = """
-----BEGIN PGP PUBLIC KEY BLOCK-----
Comment: Alice's OpenPGP certificate
Comment: https://www.ietf.org/id/draft-bre-openpgp-samples-01.html

mDMEXEcE6RYJKwYBBAHaRw8BAQdArjWwk3FAqyiFbFBKT4TzXcVBqPTB3gmzlC/U
b7O1u120JkFsaWNlIExvdmVsYWNlIDxhbGljZUBvcGVucGdwLmV4YW1wbGU+iJAE
ExYIADgCGwMFCwkIBwIGFQoJCAsCBBYCAwECHgECF4AWIQTrhbtfozp14V6UTmPy
MVUMT0fjjgUCXaWfOgAKCRDyMVUMT0fjjukrAPoDnHBSogOmsHOsd9qGsiZpgRnO
dypvbm+QtXZqth9rvwD9HcDC0tC+PHAsO7OTh1S1TC9RiJsvawAfCPaQZoed8gK4
OARcRwTpEgorBgEEAZdVAQUBAQdAQv8GIa2rSTzgqbXCpDDYMiKRVitCsy203x3s
E9+eviIDAQgHiHgEGBYIACAWIQTrhbtfozp14V6UTmPyMVUMT0fjjgUCXEcE6QIb
DAAKCRDyMVUMT0fjjlnQAQDFHUs6TIcxrNTtEZFjUFm1M0PJ1Dng/cDW4xN80fsn
0QEA22Kr7VkCjeAEC08VSTeV+QFsmz55/lntWkwYWhmvOgE=
=iIGO
-----END PGP PUBLIC KEY BLOCK-----
"""

ALICE_REVOCATION = """
-----BEGIN PGP PUBLIC KEY BLOCK-----
Comment: Alice's revocation certificate
Comment: https://www.ietf.org/id/draft-bre-openpgp-samples-01.html

iHgEIBYIACAWIQTrhbtfozp14V6UTmPyMVUMT0fjjgUCXaWkOwIdAAAKCRDyMVUM
T0fjjoBlAQDA9ukZFKRFGCooVcVoDVmxTaHLUXlIg9TPh2f7zzI9KgD/SLNXUOaH
O6TozOS7C9lwIHwwdHdAxgf5BzuhLT9iuAM=
=Tm8h
-----END PGP PUBLIC KEY BLOCK-----
"""

ALICE_REVOKED = """
-----BEGIN PGP PUBLIC KEY BLOCK-----

mDMEXEcE6RYJKwYBBAHaRw8BAQdArjWwk3FAqyiFbFBKT4TzXcVBqPTB3gmzlC/U
b7O1u12IeAQgFggAIBYhBOuFu1+jOnXhXpROY/IxVQxPR+OOBQJdpaQ7Ah0AAAoJ
EPIxVQxPR+OOgGUBAMD26RkUpEUYKihVxWgNWbFNoctReUiD1M+HZ/vPMj0qAP9I
s1dQ5oc7pOjM5LsL2XAgfDB0d0DGB/kHO6EtP2K4A7QmQWxpY2UgTG92ZWxhY2Ug
PGFsaWNlQG9wZW5wZ3AuZXhhbXBsZT6IkAQTFggAOAIbAwULCQgHAgYVCgkICwIE
FgIDAQIeAQIXgBYhBOuFu1+jOnXhXpROY/IxVQxPR+OOBQJdpZ86AAoJEPIxVQxP
R+OO6SsA+gOccFKiA6awc6x32oayJmmBGc53Km9ub5C1dmq2H2u/AP0dwMLS0L48
cCw7s5OHVLVML1GImy9rAB8I9pBmh53yArg4BFxHBOkSCisGAQQBl1UBBQEBB0BC
/wYhratJPOCptcKkMNgyIpFWK0KzLbTfHewT356+IgMBCAeIeAQYFggAIBYhBOuF
u1+jOnXhXpROY/IxVQxPR+OOBQJcRwTpAhsMAAoJEPIxVQxPR+OOWdABAMUdSzpM
hzGs1O0RkWNQWbUzQ8nUOeD9wNbjE3zR+yfRAQDbYqvtWQKN4AQLTxVJN5X5AWyb
Pnn+We1aTBhaGa86AQ==
=W1yt
-----END PGP PUBLIC KEY BLOCK-----
"""

BOB_PUB = """
-----BEGIN PGP PUBLIC KEY BLOCK-----
Comment: Bob's OpenPGP certificate
Comment: https://www.ietf.org/id/draft-bre-openpgp-samples-01.html

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
NEJd3XZRzaXZE2aAMQ==
=NXei
-----END PGP PUBLIC KEY BLOCK-----
"""

BOB_REVOCATION = """
-----BEGIN PGP PUBLIC KEY BLOCK-----
Comment: Bob's revocation certificate
Comment: https://www.ietf.org/id/draft-bre-openpgp-samples-01.html

iQG2BCABCgAgFiEE0aZuGiOxgsmYD3iM+/zIKgFeczAFAl2lnQQCHQAACgkQ+/zI
KgFeczAIHAv/RrlGlPFKsW0BShC8sVtPfbT1N9lUqyrsgBhrUryM/i+rBtkbnSjp
28R5araupt0og1g2L5VsCRM+ql0jf0zrZXOorKfAO70HCP3X+MlEquvztMUZGJRZ
7TSMgIY1MeFgLmOw9pDKf3tSoouBOpPe5eVfXviEDDo2zOfdntjPyCMlxHgAcjZo
XqMaurV+nKWoIx0zbdpNLsRy4JZcmnOSFdPw37R8U2miPi2qNyVwcyCxQy0LjN7Y
AWadrs9vE0DrneSVP2OpBhl7g+Dj2uXJQRPVXcq6w9g5Fir6DnlhekTLsa78T5cD
n8q7aRusMlALPAOosENOgINgsVcjuILkPN1eD+zGAgHgdiKaep1+P3pbo5n0CLki
UCAsLnCEo8eBV9DCb/n1FlI5yhQhgQyMYlp/49H0JSc3IY9KHhv6f0zIaRWs0JuD
ajcXTJ9AyB+SA6GBb9Q+XsNXjZ1gj75ekUD1sQ3ezTvVfovgP5bD+vPvILhSImKB
aU6V3zld/x/1
=mMwU
-----END PGP PUBLIC KEY BLOCK-----
"""

# Known fingerprints for the IETF sample keys above
ALICE_FINGERPRINT = "EB85BB5FA33A75E15E944E63F231550C4F47E38E"
BOB_FINGERPRINT = "D1A66E1A23B182C9980F788CFBFCC82A015E7330"


@pytest.mark.parallel
class TestOpenPGPKeyUpload:
    """Test uploading various OpenPGP key types."""

    @pytest.mark.parametrize(
        "key_url,fingerprint_len",
        [
            (KEY_V4_RSA2K_PUBLIC, 40),
            (KEY_V4_RSA4K_PUBLIC, 40),
            (KEY_V4_ED25519_PUBLIC, 40),
            (KEY_V6_ED25519_PUBLIC, 64),
            (KEY_V6_RSA4K_PUBLIC, 64),
            (KEY_V6_MLDSA65_ED25519_PUBLIC, 64),
            (KEY_V6_MLDSA87_ED448_PUBLIC, 64),
        ],
        ids=[
            "v4-rsa2k",
            "v4-rsa4k",
            "v4-ed25519",
            "v6-ed25519",
            "v6-rsa4k",
            "pqc-mldsa65",
            "pqc-mldsa87",
        ],
    )
    def test_upload_key(
        self,
        tmpdir,
        openpgp_keyring_factory,
        pulpcore_bindings,
        monitor_task,
        key_url,
        fingerprint_len,
    ):
        keyring = openpgp_keyring_factory()
        keyring = _upload_key_from_url(tmpdir, pulpcore_bindings, monitor_task, key_url, keyring)

        keys = pulpcore_bindings.ContentOpenpgpPublickeyApi.list(
            repository_version=keyring.latest_version_href
        )
        assert keys.count == 1
        key = keys.results[0]
        assert len(key.fingerprint) == fingerprint_len
        assert re.fullmatch(rf"[0-9A-F]{{{fingerprint_len}}}", key.fingerprint)

        user_ids = pulpcore_bindings.ContentOpenpgpUseridApi.list(
            repository_version=keyring.latest_version_href
        )
        assert user_ids.count >= 1

        signatures = pulpcore_bindings.ContentOpenpgpSignatureApi.list(
            repository_version=keyring.latest_version_href
        )
        assert signatures.count >= 1

    def test_reject_private_key_upload(
        self, tmpdir, openpgp_keyring_factory, pulpcore_bindings, monitor_task
    ):
        keyring = openpgp_keyring_factory()
        key_data = _download_key(KEY_V4_ED25519_PRIVATE)
        key_path = tmpdir / "private.key"
        key_path.write_binary(key_data)

        result = pulpcore_bindings.ContentOpenpgpPublickeyApi.create(
            file=str(key_path), repository=keyring.pulp_href
        )
        with pytest.raises(PulpTaskError) as exc_info:
            monitor_task(result.task)
        assert exc_info.value.task.state == "failed"


@pytest.mark.parallel
class TestOpenPGPKeyContent:
    """Test content listing, filtering, and structure."""

    def test_multiple_keys_in_keyring(
        self, tmpdir, openpgp_keyring_factory, pulpcore_bindings, monitor_task
    ):
        keyring = openpgp_keyring_factory()

        for url in [KEY_V4_RSA2K_PUBLIC, KEY_V4_ED25519_PUBLIC, KEY_V6_ED25519_PUBLIC]:
            keyring = _upload_key_from_url(tmpdir, pulpcore_bindings, monitor_task, url, keyring)

        keys = pulpcore_bindings.ContentOpenpgpPublickeyApi.list(
            repository_version=keyring.latest_version_href
        )
        assert keys.count == 3

        v4_keys = [k for k in keys.results if len(k.fingerprint) == 40]
        v6_keys = [k for k in keys.results if len(k.fingerprint) == 64]
        assert len(v4_keys) == 2
        assert len(v6_keys) == 1

    def test_filter_public_key_by_fingerprint(
        self, tmpdir, openpgp_keyring_factory, pulpcore_bindings, monitor_task
    ):
        keyring = openpgp_keyring_factory()
        keyring = _upload_key(tmpdir, pulpcore_bindings, monitor_task, ALICE_PUB, keyring)
        keyring = _upload_key(tmpdir, pulpcore_bindings, monitor_task, BOB_PUB, keyring)

        alice_results = pulpcore_bindings.ContentOpenpgpPublickeyApi.list(
            fingerprint=ALICE_FINGERPRINT
        )
        assert alice_results.count == 1
        assert alice_results.results[0].fingerprint == ALICE_FINGERPRINT

        bob_results = pulpcore_bindings.ContentOpenpgpPublickeyApi.list(fingerprint=BOB_FINGERPRINT)
        assert bob_results.count == 1
        assert bob_results.results[0].fingerprint == BOB_FINGERPRINT

    def test_filter_signature_by_issuer(
        self, tmpdir, openpgp_keyring_factory, pulpcore_bindings, monitor_task
    ):
        keyring = openpgp_keyring_factory()
        keyring = _upload_key(tmpdir, pulpcore_bindings, monitor_task, ALICE_PUB, keyring)

        alice_keyid = ALICE_FINGERPRINT[-16:]
        sigs = pulpcore_bindings.ContentOpenpgpSignatureApi.list(
            repository_version=keyring.latest_version_href, issuer=alice_keyid
        )
        assert sigs.count >= 1
        for sig in sigs.results:
            assert sig.issuer == alice_keyid

    def test_user_id_content(
        self, tmpdir, openpgp_keyring_factory, pulpcore_bindings, monitor_task
    ):
        keyring = openpgp_keyring_factory()
        keyring = _upload_key(tmpdir, pulpcore_bindings, monitor_task, ALICE_PUB, keyring)

        user_ids = pulpcore_bindings.ContentOpenpgpUseridApi.list(
            repository_version=keyring.latest_version_href
        )
        assert user_ids.count == 1
        assert "Alice Lovelace" in user_ids.results[0].user_id

    def test_subkey_content(self, tmpdir, openpgp_keyring_factory, pulpcore_bindings, monitor_task):
        keyring = openpgp_keyring_factory()
        keyring = _upload_key(tmpdir, pulpcore_bindings, monitor_task, ALICE_PUB, keyring)

        subkeys = pulpcore_bindings.ContentOpenpgpPublicsubkeyApi.list(
            repository_version=keyring.latest_version_href
        )
        assert subkeys.count >= 1
        for subkey in subkeys.results:
            assert len(subkey.fingerprint) == 40
            assert re.fullmatch(r"[0-9A-F]{40}", subkey.fingerprint)

    def test_idempotent_upload(
        self, tmpdir, openpgp_keyring_factory, pulpcore_bindings, monitor_task
    ):
        keyring = openpgp_keyring_factory()
        keyring = _upload_key(tmpdir, pulpcore_bindings, monitor_task, ALICE_PUB, keyring)
        keyring = _upload_key(tmpdir, pulpcore_bindings, monitor_task, ALICE_PUB, keyring)
        keys = pulpcore_bindings.ContentOpenpgpPublickeyApi.list(
            repository_version=keyring.latest_version_href
        )
        assert keys.count == 1
        assert keys.results[0].fingerprint == ALICE_FINGERPRINT

    def test_key_revocation_merged(
        self, tmpdir, openpgp_keyring_factory, pulpcore_bindings, monitor_task
    ):
        """Upload a key, then upload the same key with a revocation signature merged in."""
        keyring = openpgp_keyring_factory()
        keyring = _upload_key(tmpdir, pulpcore_bindings, monitor_task, ALICE_PUB, keyring)
        keyring = _upload_key(tmpdir, pulpcore_bindings, monitor_task, ALICE_REVOKED, keyring)
        keys = pulpcore_bindings.ContentOpenpgpPublickeyApi.list(
            repository_version=keyring.latest_version_href
        )
        assert keys.count == 1
        assert keys.results[0].fingerprint == ALICE_FINGERPRINT

        sigs = pulpcore_bindings.ContentOpenpgpSignatureApi.list(
            repository_version=keyring.latest_version_href
        )
        sig_types = {sig.signature_type for sig in sigs.results}
        assert 0x20 in sig_types, "Expected a key revocation signature (type 0x20)"

    @pytest.mark.parametrize(
        "pub_data,revocation_data",
        [
            (ALICE_PUB, ALICE_REVOCATION),
            (BOB_PUB, BOB_REVOCATION),
        ],
        ids=["alice-ed25519", "bob-rsa"],
    )
    def test_standalone_revocation_certificate(
        self,
        tmpdir,
        openpgp_keyring_factory,
        pulpcore_bindings,
        monitor_task,
        pub_data,
        revocation_data,
    ):
        """Upload a standalone revocation certificate (no public key, just the signature)."""
        keyring = openpgp_keyring_factory()
        keyring = _upload_key(tmpdir, pulpcore_bindings, monitor_task, pub_data, keyring)

        key_path = tmpdir / f"{uuid.uuid4()}.asc"
        key_path.write_text(revocation_data, "UTF-8")
        result = pulpcore_bindings.ContentOpenpgpPublickeyApi.create(
            file=str(key_path), repository=keyring.pulp_href
        )
        with pytest.raises(PulpTaskError):
            monitor_task(result.task)


@pytest.mark.parallel
class TestOpenPGPKeySerialization:
    """Test key serialization via distribution and round-trip integrity."""

    def _create_distribution(
        self, pulpcore_bindings, monitor_task, gen_object_with_cleanup, keyring
    ):
        body = {
            "base_path": str(uuid.uuid4()),
            "name": str(uuid.uuid4()),
            "repository": keyring.pulp_href,
        }
        return gen_object_with_cleanup(pulpcore_bindings.DistributionsOpenpgpApi, body)

    @pytest.mark.parametrize(
        "key_url",
        [KEY_V4_RSA2K_PUBLIC, KEY_V6_ED25519_PUBLIC, KEY_V6_MLDSA65_ED25519_PUBLIC],
        ids=["v4-rsa2k", "v6-ed25519", "pqc-mldsa65"],
    )
    def test_key_serialization_roundtrip(
        self,
        tmpdir,
        openpgp_keyring_factory,
        pulpcore_bindings,
        monitor_task,
        gen_object_with_cleanup,
        http_get,
        distribution_base_url,
        key_url,
    ):
        from pysequoia import Cert

        keyring = openpgp_keyring_factory()
        keyring = _upload_key_from_url(tmpdir, pulpcore_bindings, monitor_task, key_url, keyring)

        keys = pulpcore_bindings.ContentOpenpgpPublickeyApi.list(
            repository_version=keyring.latest_version_href
        )
        uploaded_fingerprint = keys.results[0].fingerprint

        distro = self._create_distribution(
            pulpcore_bindings, monitor_task, gen_object_with_cleanup, keyring
        )

        keyid = uploaded_fingerprint[-16:]
        download_url = distribution_base_url(distro.base_url) + f"/{keyid}.pub"
        downloaded_key = http_get(download_url)

        cert = Cert.from_bytes(downloaded_key)
        assert cert.fingerprint.upper() == uploaded_fingerprint

    def test_distribution_lists_keys(
        self,
        tmpdir,
        openpgp_keyring_factory,
        pulpcore_bindings,
        monitor_task,
        gen_object_with_cleanup,
        http_get,
        distribution_base_url,
    ):
        keyring = openpgp_keyring_factory()
        keyring = _upload_key(tmpdir, pulpcore_bindings, monitor_task, ALICE_PUB, keyring)
        keyring = _upload_key(tmpdir, pulpcore_bindings, monitor_task, BOB_PUB, keyring)

        distro = self._create_distribution(
            pulpcore_bindings, monitor_task, gen_object_with_cleanup, keyring
        )

        listing_url = distribution_base_url(distro.base_url) + "/"
        listing = http_get(listing_url)
        listing_text = listing.decode("utf-8")

        alice_keyid = ALICE_FINGERPRINT[-16:]
        bob_keyid = BOB_FINGERPRINT[-16:]
        listing_lower = listing_text.lower()
        assert f"{alice_keyid.lower()}.pub" in listing_lower
        assert f"{bob_keyid.lower()}.pub" in listing_lower


@pytest.mark.parallel
class TestOpenPGPSignatureVerification:
    """Test that keys from the keyring can verify signatures."""

    def _create_distribution(
        self, pulpcore_bindings, monitor_task, gen_object_with_cleanup, keyring
    ):
        body = {
            "base_path": str(uuid.uuid4()),
            "name": str(uuid.uuid4()),
            "repository": keyring.pulp_href,
        }
        return gen_object_with_cleanup(pulpcore_bindings.DistributionsOpenpgpApi, body)

    @pytest.mark.parametrize(
        "private_url,public_url",
        [
            (KEY_V4_ED25519_PRIVATE, KEY_V4_ED25519_PUBLIC),
            (KEY_V6_ED25519_PRIVATE, KEY_V6_ED25519_PUBLIC),
        ],
        ids=["v4-ed25519", "v6-ed25519"],
    )
    def test_verify_signature(
        self,
        tmpdir,
        openpgp_keyring_factory,
        pulpcore_bindings,
        monitor_task,
        gen_object_with_cleanup,
        http_get,
        distribution_base_url,
        private_url,
        public_url,
    ):
        from pysequoia import Cert, Sig, SignatureMode, sign, verify

        secret_data = _download_key(private_url)
        cert = Cert.from_bytes(secret_data)
        fingerprint = cert.fingerprint.upper()
        signer = cert.secrets.signer()

        test_data = b"Hello, OpenPGP!\n"
        sig_bytes = sign(signer, test_data, mode=SignatureMode.DETACHED)

        pub_data = _download_key(public_url)
        keyring = openpgp_keyring_factory()
        keyring = _upload_key(tmpdir, pulpcore_bindings, monitor_task, pub_data, keyring)

        distro = self._create_distribution(
            pulpcore_bindings, monitor_task, gen_object_with_cleanup, keyring
        )

        keyid = fingerprint[-16:]
        download_url = distribution_base_url(distro.base_url) + f"/{keyid}.pub"
        served_key = http_get(download_url)

        served_certs = Cert.split_bytes(served_key)
        sig = Sig.from_bytes(sig_bytes.encode() if isinstance(sig_bytes, str) else sig_bytes)
        result = verify(bytes=test_data, store=lambda key_ids: served_certs, signature=sig)
        assert result.valid_sigs

    def test_verify_signature_multiple_keys_in_keyring(
        self,
        tmpdir,
        openpgp_keyring_factory,
        pulpcore_bindings,
        monitor_task,
        gen_object_with_cleanup,
        http_get,
        distribution_base_url,
    ):
        """Sign with one key, verify against a keyring containing multiple keys."""
        from pysequoia import Cert, Sig, SignatureMode, sign, verify

        secret_data = _download_key(KEY_V4_ED25519_PRIVATE)
        cert = Cert.from_bytes(secret_data)
        fingerprint = cert.fingerprint.upper()
        signer = cert.secrets.signer()

        test_data = b"Hello, OpenPGP!\n"
        sig_bytes = sign(signer, test_data, mode=SignatureMode.DETACHED)

        keyring = openpgp_keyring_factory()

        pub_data = _download_key(KEY_V4_ED25519_PUBLIC)
        keyring = _upload_key(tmpdir, pulpcore_bindings, monitor_task, pub_data, keyring)
        keyring = _upload_key_from_url(
            tmpdir, pulpcore_bindings, monitor_task, KEY_V4_RSA2K_PUBLIC, keyring
        )
        keyring = _upload_key_from_url(
            tmpdir, pulpcore_bindings, monitor_task, KEY_V6_ED25519_PUBLIC, keyring
        )

        keys = pulpcore_bindings.ContentOpenpgpPublickeyApi.list(
            repository_version=keyring.latest_version_href
        )
        assert keys.count == 3

        distro = self._create_distribution(
            pulpcore_bindings, monitor_task, gen_object_with_cleanup, keyring
        )

        keyid = fingerprint[-16:]
        download_url = distribution_base_url(distro.base_url) + f"/{keyid}.pub"
        served_key = http_get(download_url)

        served_certs = Cert.split_bytes(served_key)
        sig = Sig.from_bytes(sig_bytes.encode() if isinstance(sig_bytes, str) else sig_bytes)
        result = verify(bytes=test_data, store=lambda key_ids: served_certs, signature=sig)
        assert result.valid_sigs
