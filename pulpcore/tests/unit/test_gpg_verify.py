"""Unit tests for gpg_verify covering OpenPGP v4, v6, classical, and PQC algorithms."""

import pytest
from pysequoia import CipherSuite, Profile, SignatureMode, Tsk, sign

from pulpcore.app.util import VerifyResult, gpg_verify
from pulpcore.exceptions.validation import InvalidSignatureError

# Test key configurations: (name, key_generator, description)
TEST_KEYS = [
    ("v4_ed25519", (Profile.RFC4880, None), "OpenPGP v4 Ed25519"),
    ("v6_ed25519", (Profile.RFC9580, None), "OpenPGP v6 Ed25519"),
    (
        "v6_mldsa65_ed25519",
        (Profile.RFC9580, CipherSuite.MLDSA65_Ed25519),
        "OpenPGP v6 ML-DSA-65 + Ed25519 (PQC)",
    ),
]


@pytest.fixture(params=TEST_KEYS, ids=[k[0] for k in TEST_KEYS], scope="module")
def key_pair(request):
    """Generate an ephemeral keypair once per test configuration."""
    name, key_generator, description = request.param
    profile, cipher_suite = key_generator
    tsk = Tsk.generate(
        f"Test {name} <test-{name}@example.com>",
        profile=profile,
        cipher_suite=cipher_suite,
    )
    cert = tsk.extract_certificate()

    return {
        "name": name,
        "description": description,
        "tsk": tsk,
        "pubkey": str(cert),
        "fingerprint": cert.fingerprint,
    }


@pytest.fixture
def detached_sig_fixture(key_pair, tmp_path):
    """Create a detached signature for a given key configuration."""
    data = f"test data for {key_pair['description']}".encode()

    # Sign with pysequoia
    sig_bytes = sign(key_pair["tsk"].signer(), data, mode=SignatureMode.DETACHED)
    sig_file = tmp_path / "sig.asc"
    sig_file.write_bytes(sig_bytes)

    data_file = tmp_path / "data.txt"
    data_file.write_bytes(data)

    return {
        "pubkey": key_pair["pubkey"],
        "sig_path": str(sig_file),
        "data_path": str(data_file),
        "fingerprint": key_pair["fingerprint"],
        "data": data,
        "description": key_pair["description"],
    }


@pytest.fixture
def inline_sig_fixture(key_pair, tmp_path):
    """Create an inline signature for a given key configuration."""
    data = f"inline signed data for {key_pair['description']}".encode()

    # Sign with pysequoia
    signed = sign(key_pair["tsk"].signer(), data)
    sig_file = tmp_path / "inline_sig.pgp"
    sig_file.write_bytes(signed)

    return {
        "pubkey": key_pair["pubkey"],
        "sig_path": str(sig_file),
        "fingerprint": key_pair["fingerprint"],
        "data": data,
        "description": key_pair["description"],
    }


class TestGpgVerify:
    """Test gpg_verify across all key types."""

    def test_detached_signature_valid(self, detached_sig_fixture):
        """Verify a valid detached signature for all key configurations."""
        fixture = detached_sig_fixture

        result = gpg_verify(
            fixture["pubkey"],
            fixture["sig_path"],
            detached_data=fixture["data_path"],
        )

        assert isinstance(result, VerifyResult)
        assert result.valid is True
        # pubkey_fingerprint is the primary key, fingerprint is the signing subkey
        assert result.pubkey_fingerprint.upper() == fixture["fingerprint"].upper()
        assert result.key_id == result.fingerprint[-16:].upper()
        assert result.data is None  # detached signatures return None for data

    def test_inline_signature_valid(self, inline_sig_fixture):
        """Verify inline signatures for all key configurations."""
        fixture = inline_sig_fixture

        result = gpg_verify(fixture["pubkey"], fixture["sig_path"])

        assert isinstance(result, VerifyResult)
        assert result.valid is True
        assert result.pubkey_fingerprint.upper() == fixture["fingerprint"].upper()
        assert result.key_id == result.fingerprint[-16:].upper()
        assert result.data == fixture["data"]


class TestVerifyResultAPI:
    """Test VerifyResult API completeness."""

    def test_verify_result_detached(self, tmp_path):
        """Test VerifyResult attributes for detached signatures."""
        tsk = Tsk.generate("Test <test@example.com>", profile=Profile.RFC9580)
        pubkey = str(tsk.extract_certificate())
        fingerprint = tsk.extract_certificate().fingerprint

        data = b"test data"
        sig_bytes = sign(tsk.signer(), data, mode=SignatureMode.DETACHED)

        sig_file = tmp_path / "sig.asc"
        sig_file.write_bytes(sig_bytes)

        data_file = tmp_path / "data.txt"
        data_file.write_bytes(data)

        result = gpg_verify(pubkey, str(sig_file), detached_data=str(data_file))

        # Test all attributes
        assert result.valid is True
        assert isinstance(result.fingerprint, str)
        assert len(result.fingerprint) in (40, 64)
        assert isinstance(result.pubkey_fingerprint, str)
        assert result.pubkey_fingerprint.upper() == fingerprint.upper()
        assert isinstance(result.key_id, str)
        assert result.key_id == result.fingerprint[-16:].upper()
        assert result.data is None  # detached signature

        # Test repr
        repr_str = repr(result)
        assert "VerifyResult" in repr_str
        assert "valid=True" in repr_str
        assert "fingerprint=" in repr_str
        assert "key_id=" in repr_str

    def test_verify_result_inline(self, tmp_path):
        """Test that VerifyResult.data contains plaintext for inline signatures."""
        tsk = Tsk.generate("Test <test@example.com>", profile=Profile.RFC9580)
        pubkey = str(tsk.extract_certificate())

        data = b"test data"
        signed = sign(tsk.signer(), data)

        sig_file = tmp_path / "inline_sig.pgp"
        sig_file.write_bytes(signed)

        result = gpg_verify(pubkey, str(sig_file))

        # For inline signatures, data should contain the plaintext
        assert result.valid is True
        assert result.data is not None
        assert isinstance(result.data, bytes)
        assert result.data == data


class TestGpgVerifyErrorHandling:
    """Test gpg_verify error handling."""

    def test_wrong_data(self, tmp_path):
        """Test that tampered data fails validation."""
        tsk = Tsk.generate("Test <test@example.com>", profile=Profile.RFC9580)
        pubkey = str(tsk.extract_certificate())

        data = b"original data"
        sig_bytes = sign(tsk.signer(), data, mode=SignatureMode.DETACHED)

        sig_file = tmp_path / "sig.asc"
        sig_file.write_bytes(sig_bytes)

        tampered_file = tmp_path / "tampered.txt"
        tampered_file.write_bytes(b"tampered data")

        with pytest.raises(InvalidSignatureError):
            gpg_verify(pubkey, str(sig_file), detached_data=str(tampered_file))

    def test_wrong_key(self, tmp_path):
        """Test that wrong public key fails validation."""
        tsk = Tsk.generate("Signer <signer@example.com>", profile=Profile.RFC9580)
        wrong_tsk = Tsk.generate("Wrong <wrong@example.com>", profile=Profile.RFC9580)
        wrong_pubkey = str(wrong_tsk.extract_certificate())

        data = b"test data"
        sig_bytes = sign(tsk.signer(), data, mode=SignatureMode.DETACHED)

        sig_file = tmp_path / "sig.asc"
        sig_file.write_bytes(sig_bytes)

        data_file = tmp_path / "data.txt"
        data_file.write_bytes(data)

        with pytest.raises(InvalidSignatureError):
            gpg_verify(wrong_pubkey, str(sig_file), detached_data=str(data_file))

    def test_invalid_signature_data(self, tmp_path):
        """Test that invalid signature data raises InvalidSignatureError."""
        tsk = Tsk.generate("Test <test@example.com>", profile=Profile.RFC9580)
        pubkey = str(tsk.extract_certificate())

        bad_sig_file = tmp_path / "bad_sig.asc"
        bad_sig_file.write_bytes(b"not a valid signature")

        data_file = tmp_path / "data.txt"
        data_file.write_bytes(b"some data")

        with pytest.raises(InvalidSignatureError):
            gpg_verify(pubkey, str(bad_sig_file), detached_data=str(data_file))

    def test_corrupted_signature(self, tmp_path):
        """Test that corrupted signature raises InvalidSignatureError."""
        tsk = Tsk.generate("Test <test@example.com>", profile=Profile.RFC9580)
        pubkey = str(tsk.extract_certificate())

        data = b"test data"
        sig_bytes = sign(tsk.signer(), data, mode=SignatureMode.DETACHED)

        # Corrupt the signature
        corrupted_sig = sig_bytes[:-20] + b"X" * 20

        sig_file = tmp_path / "corrupt_sig.asc"
        sig_file.write_bytes(corrupted_sig)

        data_file = tmp_path / "data.txt"
        data_file.write_bytes(data)

        with pytest.raises(InvalidSignatureError):
            gpg_verify(pubkey, str(sig_file), detached_data=str(data_file))
