Use CRC32 checksums instead of SHA256 to improve import/export performance. Cryptographic checksums aren't required as we are only verifying the integrity of the files.
