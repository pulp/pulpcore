Adds the ``pulpcore.app.pulp_insecure_md5_hashlib`` module which provides the ``new`` function.
Plugin writers should use this instead of ``hashlib.new`` to generate checksum hashers. It wraps
around ``hashlib.new`` and allows md5 to be available, even in restricted environments, when users
have specifically configured it as such using the ``ALLOWED_CONTENT_CHECKSUMS``.

