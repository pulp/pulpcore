Added the ``pulpcore.app.pulp_hashlib`` module which provides the ``new`` function and ensures only
allowed hashers listed in ``ALLOWED_CONTENT_CHECKSUMS`` can be instantiated. Plugin writers should
use this instead of ``hashlib.new`` to generate checksum hashers.
