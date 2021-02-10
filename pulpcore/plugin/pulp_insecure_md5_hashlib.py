"""A wrapper around `hashlib` which patches md5 with usedforsecurity=False"""

from pulp.app.pulp_insecure_md5_hashlib import new  # noqa
