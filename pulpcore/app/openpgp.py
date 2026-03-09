import hashlib

from pysequoia.packet import PacketPile, Tag


def read_public_key(data):
    pile = PacketPile.from_bytes(data)

    public_key = None
    signed_content = None

    for packet in pile:
        tag = packet.tag
        body = bytes(packet.body)

        if tag == Tag.PublicKey:
            if public_key is not None:
                raise ValueError("Multiple public keys found.")
            public_key = {
                "raw_data": body,
                "fingerprint": packet.fingerprint,
                "created": packet.key_created,
                "user_ids": [],
                "user_attributes": [],
                "public_subkeys": [],
                "signatures": [],
            }
            signed_content = public_key

        elif tag == Tag.PublicSubkey:
            public_subkey = {
                "raw_data": body,
                "fingerprint": packet.fingerprint,
                "created": packet.key_created,
                "signatures": [],
            }
            signed_content = public_subkey
            public_key["public_subkeys"].append(public_subkey)

        elif tag == Tag.UserID:
            user_id = {
                "raw_data": body,
                "user_id": packet.user_id,
                "signatures": [],
            }
            signed_content = user_id
            public_key["user_ids"].append(user_id)

        elif tag == Tag.UserAttribute:
            user_attribute = {
                "raw_data": body,
                "sha256": hashlib.sha256(body).hexdigest(),
                "signatures": [],
            }
            signed_content = user_attribute
            public_key["user_attributes"].append(user_attribute)

        elif tag == Tag.Signature:
            sig_attrs = {
                "sha256": hashlib.sha256(body).hexdigest(),
                "signature_type": body[1],
                "raw_data": body,
                "created": packet.signature_created,
            }
            # Note: Pulp's concept of "expiration time" is a duration starting at creation time
            # Sequoia calls that "validity_period", while "expiration_time" is an instant
            if packet.signature_validity_period is not None:
                sig_attrs["expiration_time"] = packet.signature_validity_period
            if packet.key_validity_period is not None:
                sig_attrs["key_expiration_time"] = packet.key_validity_period
            if packet.issuer_key_id is not None:
                sig_attrs["issuer"] = packet.issuer_key_id
            if packet.signers_user_id is not None:
                sig_attrs["signers_user_id"] = packet.signers_user_id
            signed_content["signatures"].append(sig_attrs)

        else:
            raise NotImplementedError(f"Unexpected packet type: {tag!r}")

    if public_key is None:
        raise ValueError("Not a public key.")

    return public_key
