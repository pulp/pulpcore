import hashlib
from base64 import b64decode, b64encode

from django.utils import timezone

# Source of information:
#   * rfc4880
#   * rfc4880bis
#   * gnupg sources
#   * https://datatracker.ietf.org/doc/html/draft-shaw-openpgp-hkp-00


PACKET_TYPES = {
    1: "Public-Key Encrypted Session Key Packet",
    2: "Signature Packet",
    3: "Symmetric-Key Encrypted Session Key Packet",
    4: "One-Pass Signature Packet",
    5: "Secret-Key Packet",
    6: "Public-Key Packet",
    7: "Secret-Subkey Packet",
    8: "Compressed Data Packet",
    9: "Symmetrically Encrypted Data Packet",
    10: "Marker Packet",
    11: "Literal Data Packet",
    12: "Trust Packet",
    13: "User ID Packet",
    14: "Public-Subkey Packet",
    17: "User Attribute Packet",
    18: "Sym. Encrypted and Integrity Protected Data Packet",
    19: "Modification Detection Code Packet",
    20: "OCB Encrypted Data Packet",
}


SIG_SUBPACKAGE_TYPES = {
    2: "Signature Creation Time",
    3: "Signature Expiration Time",
    4: "Exportable Certification",
    5: "Trust Signature",
    6: "Regular Expression",
    7: "Revocable",
    9: "Key Expiration Time",
    10: "Placeholder for backward compatibility",
    11: "Preferred Symmetric Algorithms",
    12: "Revocation Key",
    16: "Issuer",
    20: "Notation Data",
    21: "Preferred Hash Algorithms",
    22: "Preferred Compression Algorithms",
    23: "Key Server Preferences",
    24: "Preferred Key Server",
    25: "Primary User ID",
    26: "Policy URI",
    27: "Key Flags",
    28: "Signer's User ID",
    29: "Reason for Revocation",
    30: "Features",
    31: "Signature Target",
    32: "Embedded Signature",
    33: "Issuer Fingerprint",
    34: "Preferred Encryption Modes",
    35: "Intended Recipient Fingerprint",
    37: "Attested Certifications",
    38: "Key Block",
    40: "Literal Data Meta Hash",
    41: "Trust Alias",
}


PUBKEY_ALGORITHMS = {
    1: {
        "name": "RSA",
        "format": "mm",
    },
    2: {
        "name": "RSA Encrypt-Only",
        "format": "mm",
    },
    3: {
        "name": "RSA Sign-Only",
        "format": "mm",
    },
    16: {
        "name": "Elgamal",
        "format": "mmm",
    },
    17: {
        "name": "DSA",
        "format": "mmmm",
    },
    18: {
        "name": "ECDH",
        "format": "omk",
    },
    19: {
        "name": "ECDSA",
        "format": "om",
    },
    22: {
        "name": "EdDSA",
        "format": "om",
    },
}


HASH_ALGORITHMS = {
    1: "md5",
    2: "sha1",
    3: "ripemd160",
    8: "sha256",
    9: "sha384",
    10: "sha512",
    11: "sha224",
    12: "sha3-256",
    14: "sha3-512",
}


SYMMETRIC_ALGORITHMS = {
    0: "Plaintext",
    1: "IDEA",
    2: "TripleDES",
    3: "CAST5",
    4: "Blowfish",
    7: "AES128",
    8: "AES192",
    9: "AES256",
    10: "Twofish",
    11: "Camellia 128",
    12: "Camellia 192",
    13: "Camellia 256",
}


COMPRESSION_ALGORITHMS = {
    0: "Uncompressed",
    1: "ZIP",
    2: "ZLIB",
    3: "BZip2",
}


ENCRYPTION_MODES = {
    1: "EAX",
    2: "OCB",
}


def packet_iter(data):
    begin = 0
    pos = 0
    while pos < len(data):
        packet_tag = data[pos]
        pos += 1
        if not packet_tag & 0x80:
            raise ValueError("Invalid Packet Tag")
        new_format = bool(packet_tag & 0x40)

        if new_format:
            packet_type = packet_tag & 0x1F

            if data[pos] < 0xC0:
                # 1-octet length
                length = data[pos]
                pos += 1
            elif data[pos] < 0xE0:
                # 2-octet length
                length = ((data[pos] - 0xC0) << 8) + data[pos + 1] + 0xC0
                pos += 2
            elif data[pos] == 0xFF:
                # 5-octet length
                length = int.from_bytes(data[pos + 1 : pos + 5], "big")
                pos += 5
            else:
                # Partial body length
                raise NotImplementedError("Partial Packet Body is not implemented")
        else:
            packet_type = (packet_tag & 0x3C) >> 2
            length_type = packet_tag & 0x03
            if length_type == 3:
                # Indeterminate packet length
                length = len(data) - pos
            else:
                length_bytes = 1 << length_type
                length = int.from_bytes(data[pos : pos + length_bytes], "big")
                pos += length_bytes

        if packet_type == 0:
            raise ValueError("Invalid Packet Type")
        yield {
            "type": packet_type,
            "body": data[pos : pos + length],
            "raw": data[begin : pos + length],
        }
        pos += length
        begin = pos
    if pos != len(data):
        raise ValueError("Broken Stream")


def subpacket_iter(data):
    begin = 0
    pos = 0
    while pos < len(data):
        if data[pos] < 0xC0:
            # 1-octet length
            length = data[pos]
            pos += 1
        elif data[pos] < 0xD0:
            # 2-octet length
            length = ((data[pos] - 0xC0) << 8) + data[pos + 1] + 0xC0
            pos += 2
        elif data[pos] == 0xFF:
            # 5-octet length
            length = int.from_bytes(data[pos + 1 : pos + 5], "big")
            pos += 5
        else:
            raise ValueError("Partial packet lengths are not allowed.")
        yield {
            "type": data[pos] & 0x7F,
            "critical": bool(data[pos] & 0x80),
            "body": data[pos + 1 : pos + length],
            "raw": data[begin : pos + length],
        }
        pos += length
        begin = pos
    if pos != len(data):
        raise ValueError("Broken Stream")


def extract_mpi(data):
    bit_length = int.from_bytes(data[0 : 0 + 2], "big")
    length = (bit_length + 7) // 8
    return {"bit_length": bit_length, "body": data[2 : 2 + length], "raw": data[0 : 2 + length]}


def extract_oid_kdf(data):
    # These two types use the same method to decribe the length, which is all we want.
    length = data[0]
    return {"body": data[1 : 1 + length], "raw": data[0 : 1 + length]}


def analyze_sig_subpackets(data):
    signature_attributes = {}
    for packet in subpacket_iter(data):
        packet_type = packet["type"]
        body = packet["body"]
        if packet_type == 2:
            signature_attributes["created"] = timezone.datetime.fromtimestamp(
                int.from_bytes(body, "big")
            ).astimezone()
        elif packet_type == 3:
            signature_attributes["expiration_time"] = timezone.timedelta(
                seconds=int.from_bytes(body, "big")
            )
        elif packet_type == 9:
            signature_attributes["key_expiration_time"] = timezone.timedelta(
                seconds=int.from_bytes(body, "big")
            )
        elif packet_type == 16:
            signature_attributes["issuer"] = body.hex()
        elif packet_type == 28:
            signature_attributes["signers_user_id"] = body.decode()
    return signature_attributes


def analyze_signature(data, pubkey, signed_packet_type, signed_packet):
    # Type 2
    version = data[0]
    if version == 3:
        raise NotImplementedError("Version 3 signatures are not implemented.")
    elif version in [4, 5]:
        signature_type = data[1]
        # pubkey_algorithm = PUBKEY_ALGORITHMS.get(data[2])  # Unused here.
        hash_algorithm = HASH_ALGORITHMS.get(data[3])
        hashed_size = (data[4] << 8) + data[5]
        hashed_data = data[6 : 6 + hashed_size]
        unhashed_size = (data[6 + hashed_size] << 8) + data[7 + hashed_size]
        unhashed_data = data[8 + hashed_size : 8 + hashed_size + unhashed_size]
        canary = data[8 + hashed_size + unhashed_size : 10 + hashed_size + unhashed_size]
        # signature = data[10 + hashed_size + unhashed_size :]  # Unused here.

        if signature_type in [0x18, 0x19, 0x28]:
            # 0x18 Subkey Binding Signature
            # 0x19 Primary Key Binding Signature
            # 0x28 Subkey Revocation Signature
            if signed_packet_type != 14:
                raise ValueError("Out of band subkey key signature.")
            if version == 4:
                hash_payload = b"\x99" + len(signed_packet).to_bytes(2, "big") + signed_packet
            else:  # version == 5
                hash_payload = b"\x9a" + len(signed_packet).to_bytes(4, "big") + signed_packet
        elif signature_type in [0x10, 0x11, 0x12, 0x13, 0x16, 0x30]:
            # 0x10 - 0x13 Certification of a user id or attribute
            # 0x16 Attested Key Signature
            # 0x30 Certification Revocation Signature
            if signed_packet_type == 13:
                hash_payload = b"\xb4" + len(signed_packet).to_bytes(4, "big") + signed_packet
            elif signed_packet_type == 17:
                hash_payload = b"\xd1" + len(signed_packet).to_bytes(4, "big") + signed_packet
            else:
                raise ValueError("Out of band user ID or attribute signature.")
        elif signature_type in [0x1F, 0x20, 0x30]:
            # 0x1F Direct Key Signature
            # 0x20 Key Revocation Signature
            # 0x30 Certification Revocation Signature
            if signed_packet_type != 6:
                raise ValueError("Out of band key signature.")
            hash_payload = b""
        else:
            # 0x50 Third-Party Confirmation Signature (does this even apply to keys?)
            raise NotImplementedError(f"Unsupported signature type {signature_type:#x}.")

        # Validate the signature against the canary value
        if hash_algorithm is None:
            raise ValueError(f"Unknown hash algorithm {data[3]:#x} used for signature.")
        h = hashlib.new(hash_algorithm)
        if version == 4:
            h.update(b"\x99" + len(pubkey).to_bytes(2, "big") + pubkey)
        else:  # version == 5
            h.update(b"\x9a" + len(pubkey).to_bytes(4, "big") + pubkey)
        h.update(hash_payload)
        if version == 4:
            h.update(
                data[: 6 + hashed_size]
                + b"\x04\xff"
                + ((6 + hashed_size) % (1 << 32)).to_bytes(4, "big")
            )
        else:  # version == 5
            h.update(
                data[: 6 + hashed_size]
                + b"\x05\xff"
                + ((6 + hashed_size) % (1 << 64)).to_bytes(8, "big")
            )
        if not h.digest().startswith(canary):
            raise ValueError("Signature canary mismatch")

        # Hash the signature packet for db-uniqueness
        sha256 = hashlib.sha256(data).hexdigest()
        signature_attributes = {
            "sha256": sha256,
            "signature_type": signature_type,
            "raw_data": data,
        }
        # Hashed Subpackets
        signature_attributes.update(analyze_sig_subpackets(hashed_data))
        # Unhashed Subpackets
        signature_attributes.update(analyze_sig_subpackets(unhashed_data))
        return signature_attributes
    else:
        raise ValueError(f"Invalid Packet version {version}")


def analyze_user_id(data):
    # Type 13
    user_id = data.decode()
    return {"raw_data": data, "user_id": user_id}


def analyze_user_attribute(data):
    # Type 17
    # Treat as an opaque packet for now.
    sha256 = hashlib.sha256(data).hexdigest()
    return {"raw_data": data, "sha256": sha256}


def analyze_pubkey(data):
    # Type 5, 6, 7 or 14
    # Type 5 and 7 are actually secret key packages. They begin with the corresponding public key
    # package. Secret bits are ignored by us here.
    version = data[0]
    created = timezone.datetime.fromtimestamp(int.from_bytes(data[1:5], "big")).astimezone()
    if version == 3:
        n = extract_mpi(data[8:])
        e = extract_mpi(data[8 + len(n["raw"])])
        fingerprint = hashlib.md5(n["body"] + e["body"]).hexdigest()
        # expiration = int.from_bytes(data[5:7], "big")  # Unused here. Kept for documentation.
        pubkey_algorithm = PUBKEY_ALGORITHMS.get(data[7])
    elif version in [4, 5]:
        pubkey_algorithm = PUBKEY_ALGORITHMS.get(data[5])
        if version == 4:
            key_data = data[6:]
        else:
            key_data_len = int.from_bytes(data[6:10], "big")
            key_data = data[10 : 10 + key_data_len]
            pub_key_body = data[: 10 + key_data_len]
            fingerprint = hashlib.sha256(
                b"\x9a" + len(pub_key_body).to_bytes(4, "big") + pub_key_body
            ).hexdigest()
        if pubkey_algorithm and "format" in pubkey_algorithm:
            pos = 0
            for item_type in pubkey_algorithm["format"]:
                if item_type == "m":
                    # Multi precision integer
                    mpi = extract_mpi(key_data[pos:])
                    pos += len(mpi["raw"])
                elif item_type == "o":
                    # OID
                    oid = extract_oid_kdf(key_data[pos:])
                    pos += len(oid["raw"])
                elif item_type == "k":
                    # KDF parameters
                    kdf = extract_oid_kdf(key_data[pos:])
                    pos += len(kdf["raw"])
                else:
                    raise RuntimeError("Unknown key material format.")
            if version == 4:
                key_data_len = pos
                pub_key_body = data[: 6 + key_data_len]
                fingerprint = hashlib.sha1(
                    b"\x99" + len(pub_key_body).to_bytes(2, "big") + pub_key_body
                ).hexdigest()
        else:
            if version == 4:
                # We needed to analyse the public key algorithm to calculate the fingerprint of
                # version 4 keys. Version 5 keys do not have this limitation, and we can get away
                # with an unknown algorithm.
                raise ValueError("Unknown public key algorithm.")
    else:
        raise ValueError(f"Invalid Packet version {version}")
    return {"raw_data": data, "created": created, "fingerprint": fingerprint}


def gpg_crc24(data):
    crc = 0xB704CE
    for byte in data:
        crc ^= byte << 16
        for i in range(8):
            crc <<= 1
            if crc & 0x1000000:
                crc ^= 0x1864CFB
    return (crc & 0xFFFFFF).to_bytes(3, "big")


def unwrap_armor(data):
    try:
        lines = data.decode().strip().split("\n")
    except UnicodeDecodeError:
        # assume raw binary data
        return data
    line = lines.pop(0).strip()
    if line.startswith("-----BEGIN ") and line.endswith("-----"):
        message_type = line[11:-5]
    else:
        # Header not found assume raw binary data
        return data
    line = lines.pop(0).strip()
    while line != "":
        # Armor Headers
        line = lines.pop(0).strip()
    armor = ""
    while line != "-----END " + message_type + "-----":
        armor += line
        line = lines.pop(0).strip()
    if armor[-5] != "=":
        raise ValueError("Broken Stream")
    raw = b64decode(armor[:-5])
    checksum = b64decode(armor[-4:])
    if gpg_crc24(raw) != checksum:
        raise ValueError("Checksum Mismatch")
    return raw


def wrap_armor(raw, message_type="PGP PUBLIC KEY BLOCK"):
    checksum = "=" + b64encode(gpg_crc24(raw)).decode()
    data = b64encode(raw).decode()
    lines = ["-----BEGIN " + message_type + "-----", ""]
    while data:
        line = data[:76]
        data = data[76:]
        lines.append(line)
    lines.append(checksum)
    lines.append("-----END " + message_type + "-----")
    return "\n".join(lines)


def read_public_key(data):
    data = unwrap_armor(data)
    packets = packet_iter(data)

    # The first packet must be the public key.
    packet = next(packets)
    if packet["type"] != 6:
        raise ValueError("Not a public key.")
    public_key = analyze_pubkey(packet["body"])
    public_key.update(
        {"user_ids": [], "user_attributes": [], "public_subkeys": [], "signatures": []}
    )
    signed_content = public_key
    signed_packet_type = 6

    for packet in packets:
        packet_type = packet["type"]
        body = packet["body"]
        if packet_type == 2:
            signed_content["signatures"].append(
                analyze_signature(
                    body,
                    public_key["raw_data"],
                    signed_packet_type,
                    signed_content["raw_data"],
                )
            )

        elif packet_type == 13:
            user_id = analyze_user_id(body)
            user_id["signatures"] = []
            signed_content = user_id
            signed_packet_type = packet_type
            public_key["user_ids"].append(user_id)

        elif packet_type == 14:
            public_subkey = analyze_pubkey(body)
            public_subkey["signatures"] = []
            signed_content = public_subkey
            signed_packet_type = packet_type
            public_key["public_subkeys"].append(public_subkey)

        elif packet_type == 17:
            user_attribute = analyze_user_attribute(body)
            user_attribute["signatures"] = []
            signed_content = user_attribute
            signed_packet_type = packet_type
            public_key["user_attributes"].append(user_attribute)

        else:
            raise NotImplementedError("Invalid or unknown rfc4880 packet.")

    return public_key
