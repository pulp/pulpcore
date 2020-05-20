from __future__ import absolute_import, division, print_function

__metaclass__ = type


ANSIBLE_METADATA = {
    "metadata_version": "1.1",
    "status": ["preview"],
    "supported_by": "community",
}


def _repr_filter(value):
    return repr(value)


# ---- Ansible filters ----
class FilterModule(object):
    """Repr filter."""

    def filters(self):
        """Filter associations."""
        return {
            "repr": _repr_filter,
        }
