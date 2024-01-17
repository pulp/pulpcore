from gettext import gettext as _

from django.core.exceptions import ImproperlyConfigured

try:
    import rhsm  # rhsm is an optional dependency
except ImportError as e:
    rhsm = None
    rhsm_import_error = str(e)


def get_rhsm():
    """
    Returns the `rhsm` module or raises an exception if `rhsm` is not installed.

    `rhsm` is an optional dependency so you can call this function to get `rhsm` or have an
    `ImproperlyConfigured` error for the user.

    Returns:
        The `rhsm` Python module.

    Raises:
        `ImproperlyConfigured` exception explaining `rhsm` is not installed.
    """
    if rhsm is None:
        error_msg = _("RHSMCertGuard requires the Python package 'rhsm' to be installed ({}).")
        raise ImproperlyConfigured(error_msg.format(rhsm_import_error))
    return rhsm
