import typing as t
from cryptography import x509
from heapq import heappush, heappop
import itertools
import re
import zlib


RH_OID = "1.3.6.1.4.1.2312.9"
RH_ORDER_NAME_OID = RH_OID + ".4.1"
RH_VERSION_OID = RH_OID + ".6"
RH_ENTITLEMENT_OID = RH_OID + ".7"
V1_PATH_OID_REGEX = re.compile(rf"^{re.escape(RH_OID)}\.2\.\d+\.1\.6$")


T = t.TypeVar("T")
RecursiveDict = t.Dict[str, "RecursiveDict"]


# Proper anntoation of generic classes was introduced in Python 3.12
# class HuffmannNode[T]
class HuffmannNode:
    def __init__(
        self,
        left: "t.Self | T",
        right: "t.Self | T",
    ) -> None:
        self.left: "t.Self | T" = left
        self.right: "t.Self | T" = right

    @classmethod
    def build_tree(cls, items: t.Iterable[T]) -> "t.Self":
        # This builds a special type of tree, where the weights are _always_ like 1,2,3,...
        serial = itertools.count(1)  # Used to keep items of equal weight in order.
        heap: list[tuple[int, int, "t.Self | T"]] = []
        for value in items:
            weight = next(serial)
            # First item is the actual weight, second is the tiebreaker.
            # Values are never compared.
            heappush(heap, (weight, weight, value))
        while True:
            lw, _, left = heappop(heap)
            try:
                rw, _, right = heappop(heap)
                node = cls(left=left, right=right)
                heappush(heap, (lw + rw, next(serial), node))
            except IndexError:
                assert isinstance(left, cls)
                return left

    def decode(self, bitstream: t.Iterator[bool]) -> T:
        node = self.right if next(bitstream) else self.left
        if isinstance(node, self.__class__):
            return node.decode(bitstream)
        else:
            return t.cast(T, node)


def split_count(v: bytes) -> tuple[int, bytes]:
    if v[0] & 128:
        len_count = v[0] - 128
        length = 0
        for i in range(len_count):
            length <<= 8
            length += v[i + 1]
    else:
        len_count = 0
        length = int(v[0])
    return length, v[len_count + 1 :]


def asn1_string(v: bytes) -> str:
    assert v[0] == 12
    length, rest = split_count(v[1:])
    result = rest.decode()
    assert len(result) == length
    return result


def asn1_bytes(v: bytes) -> bytes:
    assert v[0] == 4
    length, result = split_count(v[1:])
    assert len(result) == length
    return result


def cert_version(cert: x509.Certificate) -> str:
    return next(
        (
            asn1_string(ext.value.value)
            for ext in cert.extensions
            if ext.oid.dotted_string == RH_VERSION_OID
        ),
        "1.0",
    )


def is_v1_entitlement(cert: x509.Certificate) -> bool:
    return any((ext for ext in cert.extensions if ext.oid.dotted_string == RH_ORDER_NAME_OID))


def v1_paths(cert: x509.Certificate) -> t.Iterator[str]:
    for ext in cert.extensions:
        if V1_PATH_OID_REGEX.match(ext.oid.dotted_string):
            yield asn1_string(ext.value.value)


def check_path_v1(cert: x509.Certificate, normalized_path: str) -> bool:
    assert is_v1_entitlement(cert)
    for cert_path in v1_paths(cert):
        # We build a regex here, nicely escaped, from the cert_path,
        # that translates the '$variables' to regex wildcards.
        path_regex = (
            r"^"
            + r"[^/]+".join(map(re.escape, re.split(r"\$[^/]*", cert_path.strip("/"))))
            + r"($|/)"
        )
        if re.match(path_regex, normalized_path):
            return True
    return False


def bitstream(data: bytes) -> t.Iterator[bool]:
    for b in data:
        for i in range(8):
            yield (b << i) & 128 != 0


class Entitlement:
    def __init__(self, cert: x509.Certificate):
        payload = self._read_payload(cert)
        lex_data, node_count, path_data = self._split_payload(payload)
        word_tree = self._build_word_tree(lex_data)
        self._path_tree = self._build_path_tree(word_tree, node_count, path_data)

    @staticmethod
    def _read_payload(cert: x509.Certificate) -> bytes:
        return asn1_bytes(
            next(
                ext.value.value
                for ext in cert.extensions
                if ext.oid.dotted_string == RH_ENTITLEMENT_OID
            )
        )

    @staticmethod
    def _split_payload(payload: bytes) -> tuple[bytes, int, bytes]:
        decobj = zlib.decompressobj()
        lex_data = decobj.decompress(payload)
        node_count, path_data = split_count(decobj.unused_data)
        return lex_data, node_count, path_data

    @staticmethod
    def _build_word_tree(lex_data: bytes) -> "HuffmannNode[str]":
        words = [item.decode() for item in lex_data.split(b"\x00")]
        assert len(words) > 1
        return HuffmannNode.build_tree(words)

    @staticmethod
    def _build_path_tree(
        word_tree: "HuffmannNode[str]", node_count: int, path_data: bytes
    ) -> RecursiveDict:
        path_nodes: list[RecursiveDict] = [{} for _ in range(node_count)]
        address_tree: "HuffmannNode[RecursiveDict]" = HuffmannNode.build_tree(path_nodes[1:])
        bitsource = bitstream(path_data)
        for node in path_nodes:
            while True:
                word = word_tree.decode(bitsource)
                if word == "":
                    break
                assert word not in node
                node[word] = address_tree.decode(bitsource)
        return path_nodes[0]

    @classmethod
    def _check_path_tree(cls, node: RecursiveDict, segments: t.List[str]) -> bool:
        if len(node) == 0:
            return True
        if len(segments) == 0:
            return False
        segment = segments[0]
        segments = segments[1:]
        for key, child in node.items():
            if (segment == key or key[0] == "$") and cls._check_path_tree(child, segments):
                return True
        return False

    def check_path(self, normalized_path: str) -> bool:
        segments = normalized_path.split("/")
        return self._check_path_tree(self._path_tree, segments)


def check_path(cert: x509.Certificate, path: str) -> bool:
    normalized_path = re.sub(r"/+", "/", path.strip("/"))
    if int(cert_version(cert).split(".")[0]) >= 3:
        return Entitlement(cert).check_path(normalized_path)
    else:
        return check_path_v1(cert, normalized_path)
