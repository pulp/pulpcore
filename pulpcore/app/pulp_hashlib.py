"""A wrapper around `hashlib` providing only hashers named in settings.ALLOWED_CONTENT_CHECKSUMS"""

from gettext import gettext as _
import hashlib as the_real_hashlib

from django.conf import settings


def new(name, *args, **kwargs):
    """
    A wrapper around the real `hashlib.new()` providing only trusted hashers.

    The `ALLOWED_CONTENT_CHECKSUMS` setting identifies which hashers are allowed for use by Pulp.
    This function raises an exception if a hasher is requested which is not allowed, and otherwise,
    returns the standard hasher from `hashlib.new()`.

    Args:
        name: The name of the hasher to be instantiated.
        *args: args to be passed along to the real `hashlib.new()`.
        **kwargs: kwargs to be passed along to the real `hashlib.new()`

    Returns:
        An instantiated hasher, if it is allowed according to `ALLOWED_CONTENT_CHECKSUMS` setting.

    Raises:
        An exception if the name of the hasher is not in the `ALLOWED_CONTENT_CHECKSUMS` settings.

    """
    if name not in settings.ALLOWED_CONTENT_CHECKSUMS:
        raise Exception(
            _(
                "Hasher {} attempted to be used but is not in the `ALLOWED_CONTENT_CHECKSUMS` "
                "setting"
            ).format(name)
        )
    return the_real_hashlib.new(name, *args, **kwargs)
