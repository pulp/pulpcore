from cryptography import x509
import pytest

from . import certdata

from pulp_certguard.rhsm import check_path
from pulp_certguard.rhsm.rhsm_check_path import (
    bitstream,
    Entitlement,
    HuffmannNode,
    cert_version,
    split_count,
    V1_PATH_OID_REGEX,
)


@pytest.fixture(scope="session")
def ent_v1() -> x509.Certificate:
    return x509.load_pem_x509_certificate(certdata.ENTITLEMENT_CERT_V1_0.encode())


@pytest.fixture(scope="session")
def ent_v3_0() -> x509.Certificate:
    return x509.load_pem_x509_certificate(certdata.ENTITLEMENT_CERT_V3_0.encode())


@pytest.fixture(scope="session")
def ent_v3_2() -> x509.Certificate:
    return x509.load_pem_x509_certificate(certdata.ENTITLEMENT_CERT_V3_2.encode())


@pytest.fixture(scope="session", params=["3.0", "3.2"])
def ent_v3_version(request: pytest.FixtureRequest) -> str:
    return request.param


@pytest.fixture(scope="session")
def ent_v3(ent_v3_version: str) -> x509.Certificate:
    ver = ent_v3_version.replace(".", "_")
    attribute = f"ENTITLEMENT_CERT_V{ver}"
    return x509.load_pem_x509_certificate(getattr(certdata, attribute).encode())


class TestSplitCount:
    """
    If the first byte is < 128, that is the count itself.
    Otherwise the 7 lsb describe the number of bytes to combine to the count.
    """

    @pytest.mark.parametrize(
        "header, count",
        [
            pytest.param(b"\x00", 0, id="short zero"),
            pytest.param(b"\x0a", 10, id="short ten"),
            pytest.param(b"\x7f", 127, id="short max"),
            pytest.param(b"\x80", 0, id="zero bytes zero"),
            pytest.param(b"\x81\x00", 0, id="one byte zero"),
            pytest.param(b"\x81\x01", 1, id="one byte one"),
            pytest.param(b"\x81\xff", 255, id="one byte max"),
            pytest.param(b"\x84\x00\x00\x00\x00", 0, id="four bytes zero"),
            pytest.param(b"\x84\x00\x00\x00\x01", 1, id="four bytes one"),
            pytest.param(b"\x84\x00\x00\x01\x00", 256, id="four bytes 256"),
            pytest.param(b"\x84\x00\x00\x01\x04", 260, id="four bytes 260"),
        ],
    )
    def test_returns_count_from(self, header: bytes, count: int) -> None:
        assert split_count(header + b"\xde\xad\xbe\xaf") == (count, b"\xde\xad\xbe\xaf")


class TestBitstream:
    def test_0000_produces_16_false(self) -> None:
        assert list(bitstream(b"\x00\x00")) == [False] * 16

    def test_0001_produces_15_false_true(self) -> None:
        assert list(bitstream(b"\x00\x01")) == [False] * 15 + [True]

    def test_fff0_produces_12_true_4_false(self) -> None:
        assert list(bitstream(b"\xff\xf0")) == [True] * 12 + [False] * 4


def test_product_certificate_has_subject() -> None:
    cert = x509.load_pem_x509_certificate(certdata.PRODUCT_CERT_V1_0.encode())
    assert cert.subject.rfc4514_string() == "CN=100000000000002"


class TestV1EntitlementCertificate:
    def test_has_subject(self, ent_v1: x509.Certificate) -> None:
        assert ent_v1.subject.rfc4514_string() == "CN=ff80808138574bd20138574d85a50b2f"

    def test_has_4_paths(self, ent_v1: x509.Certificate) -> None:
        assert (
            len(
                [ext for ext in ent_v1.extensions if V1_PATH_OID_REGEX.match(ext.oid.dotted_string)]
            )
            == 4
        )

    def test_has_version_1_0(self, ent_v1: x509.Certificate) -> None:
        assert cert_version(ent_v1) == "1.0"


class TestV3EntitlementCertificate:
    def test_cert_version(self, ent_v3_version: str, ent_v3: x509.Certificate) -> None:
        assert cert_version(ent_v3) == ent_v3_version


class TestEntitlement:
    @pytest.fixture(scope="class")
    def entitlement(self, ent_v3: x509.Certificate) -> Entitlement:
        return Entitlement(ent_v3)

    @pytest.fixture(scope="class")
    def word_tree(self, ent_v3: x509.Certificate) -> "HuffmannNode[str]":
        lex_data, _, _ = Entitlement._split_payload(Entitlement._read_payload(ent_v3))
        return Entitlement._build_word_tree(lex_data)

    def test_has_node_count_10(self, ent_v3: x509.Certificate) -> None:
        _, node_count, _ = Entitlement._split_payload(Entitlement._read_payload(ent_v3))
        assert node_count == 10

    def test_00_decodes_to_empty(self, word_tree: "HuffmannNode[str]") -> None:
        assert word_tree.decode(iter([False, False])) == ""

    def test_100_decodes_to_path(self, word_tree: "HuffmannNode[str]") -> None:
        assert word_tree.decode(iter([True, False, False])) == "path"

    def test_path_tree_root_contains_foo_and_path(self, entitlement: Entitlement) -> None:
        assert {"foo", "path"} == entitlement._path_tree.keys()

    def test_path_tree_contains_foo_path_never(self, entitlement: Entitlement) -> None:
        assert entitlement._path_tree["foo"]["path"]["never"] == {}

    def test_path_tree_contains_foo_path_var_always(self, entitlement: Entitlement) -> None:
        assert entitlement._path_tree["foo"]["path"]["always"]["$releasever"] == {}


class TestCheckPathV1:
    @pytest.mark.parametrize(
        "path",
        (
            "/foo/path/never",
            "/foo/path/never/",
            "//foo/path/never/",
            "/foo/path/never/bar/a/b/c",
            "/foo/path/never/bar//a/b/c",
            "/foo//path/never/bar//a/b/c",
        ),
    )
    def test_matches_foo_path_never(self, ent_v1: x509.Certificate, path: str) -> None:
        assert check_path(ent_v1, path)

    @pytest.mark.parametrize(
        "path",
        (
            pytest.param("/path/never", id="misses the first part"),
            pytest.param("foo", id="is only the middle part"),
            "/foo",
            "/foo/",
            pytest.param("/foo/path/", id="misses the last part"),
            pytest.param("baz/foo/path/never", id="prepended parts"),
            pytest.param("/path/to//bar/awesomeos", id="substituted an empty string"),
            pytest.param("/path/to/foo/bar/awesomeo", id="misses the last character"),
            pytest.param("/path/to/foo/bar/awesomeos1", id="adds characters at the end"),
        ),
    )
    def test_rejects_a_path_that(self, ent_v1: x509.Certificate, path: str) -> None:
        assert not check_path(ent_v1, path)

    @pytest.mark.parametrize(
        "path",
        (
            "/path/to/foo/bar/awesomeos",
            "/path/to/foo/bar/awesomeos/",
            "/path/to/foo/bar/awesomeos/a/b/c",
            "/path/to//bar/foo/awesomeos",
        ),
    )
    def test_matches_path_with_substituted_variables(
        self, ent_v1: x509.Certificate, path: str
    ) -> None:
        assert check_path(ent_v1, path)


class TestCheckPathV3:
    @pytest.mark.parametrize(
        "path",
        (
            pytest.param("/foo/path/never", id="exact path without vars"),
            pytest.param("/foo/path/never/a/b/c", id="exact path with extra segments"),
            pytest.param(
                "////foo///path//never///", id="exact path without vars and extra slashes"
            ),
            pytest.param("foo/path/always/c-3po", id="exact path with variable"),
            pytest.param("/path/to/awesomeos/x86_64", id="another exact path without vars"),
            pytest.param("/path/to/c-3po/r2-d2/awesomeos", id="another exact path with vars"),
        ),
    )
    def test_matches(self, ent_v3: x509.Certificate, path: str) -> None:
        assert check_path(ent_v3, path)

    @pytest.mark.parametrize(
        "path",
        (
            pytest.param("/a/path/to/wherever", id="lunatic path"),
            pytest.param("", id="empty path"),
            pytest.param("////", id="just slashes"),
            pytest.param("foo", id="to short path"),
            pytest.param("path/never", id="path with front segment missing"),
            pytest.param("content/foo/path/never", id="path with extra front segment"),
        ),
    )
    def test_rejects(self, ent_v3: x509.Certificate, path: str) -> None:
        assert not check_path(ent_v3, path)
