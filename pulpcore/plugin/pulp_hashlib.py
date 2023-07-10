"""A wrapper around `hashlib` providing only hashers named in settings.ALLOWED_CONTENT_CHECKSUMS"""

from pulpcore.app.pulp_hashlib import new  # noqa: F401
