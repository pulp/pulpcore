"""A wrapper around `hashlib` which patches md5 with usedforsecurity=False"""

import hashlib as the_real_hashlib


def new(name, *args, **kwargs):
    """
    A wrapper around the real `hashlib.new()` which specifies usedforsecurity=False for md5.

    Pulp by default does not allow md5 or sha1 to be used, so if this is being called with
    `name='md5'` a user has added that to the `ALLOWED_CONTENT_CHECKSUMS` list. By doing so they
    accept the are choosing to use md5 even in restricted environments. This wrapper allows them to
    do so.

    Args:
        name: The name of the hasher to be instantiated.
        *args: args to be passed along to the real `hashlib.new()`.
        **kwargs: kwargs to be passed along to the real `hashlib.new()`

    Returns:
        An instantiated hasher.
    """
    if name == "md5":
        try:
            return the_real_hashlib.new(name, *args, usedforsecurity=False, **kwargs)
        except TypeError:
            pass
    return the_real_hashlib.new(name, *args, **kwargs)
