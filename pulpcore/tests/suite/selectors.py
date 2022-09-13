# coding=utf-8
"""Tools for selecting and deselecting tests."""
import aiohttp
import asyncio
import warnings
from collections import namedtuple
from functools import wraps

from packaging.version import Version

# These are all possible values for a bug's "status" field.
#
# These statuses apply to bugs filed at https://pulp.plan.io. They are ordered
# according to an ideal workflow. As of this writing, these is no canonical
# public source for this information. But see:
# http://docs.pulpproject.org/en/latest/dev-guide/contributing/bugs.html#fixing
_UNTESTABLE_BUGS = frozenset(
    (
        "NEW",  # bug just entered into tracker
        "ASSIGNED",  # bug has been assigned to an engineer
        "POST",  # bug fix is being reviewed by dev ("posted for review")
    )
)
_TESTABLE_BUGS = frozenset(
    (
        "MODIFIED",  # bug fix has been accepted by dev
        "ON_QA",  # bug fix is being reviewed by qe
        "VERIFIED",  # bug fix has been accepted by qe
        "CLOSED - COMPLETE",
        "CLOSED - CURRENTRELEASE",
        "CLOSED - DUPLICATE",
        "CLOSED - NOTABUG",
        "CLOSED - WONTFIX",
        "CLOSED - WORKSFORME",
    )
)

# A mapping between bug IDs and bug statuses. Used by `_get_bug`.
#
# Bug IDs and statuses should be integers and strings, respectively. Example:
#
#     _BUG_STATUS_CACHE[1356] → _Bug(status='NEW', target_platform_release=…)
#     _BUG_STATUS_CACHE['1356'] → KeyError
#
_BUG_STATUS_CACHE = {}


# Information about a Pulp bug. (See: https://pulp.plan.io)
#
# The 'status' attribute is a string, such as 'NEW' or 'ASSIGNED'. The
# 'target_platform_release' attribute is a Version() object.
_Bug = namedtuple("_Bug", ("status", "target_platform_release"))


def _get_tpr(bug_json):
    """Return a bug's Target Platform Release (TPR) field.

    :param bug_json: A JSON representation of a Pulp bug. (For example, see:
        https://pulp.plan.io/issues/1.json)
    :returns: A ``packaging.version.Version`` object.
    :raises pulp_smash.exceptions.BugTPRMissingError: If no "Target Platform
        Release" field is found in ``bug_json``.
    """
    custom_field_id = 4
    custom_fields = bug_json["issue"]["custom_fields"]
    for custom_field in custom_fields:
        if custom_field["id"] == custom_field_id:
            return custom_field["value"]
    raise RuntimeError(
        'Bug {} has no custom field with ID {} ("Target Platform Release"). '
        "Custom fields: {}".format(bug_json["issue"]["id"], custom_field_id, custom_fields)
    )


def _convert_tpr(version_string):
    """Convert a Target Platform Release (TPR) string to a ``Version`` object.

    By default, a bug's TPR string is an empty string. It is unlikely to be set
    until a fix has been implemented, and even then, it is quite possible that
    the field will be left as an empty string. (Perhaps the user forgot to set
    it, or set it to the wrong value.)

    If ``version_string == ''``, this method pretends that ``version_string ==
    '0'``. Why is this useful? Let's imagine that a bug has a status of
    MODIFIED and a TPR of "": we can now assume that this bug is fixed in all
    versions of Pulp. More generally, any time a bug is marked as fixed and no
    TPR listed, we assume that the bug is fixed for all versions of Pulp.

    :param version_string: A version string like "2.8.1" or "".
    :returns: A ``packaging.version.Version`` object.
    :raises: ``packaging.version.InvalidVersion`` if ``version_string`` is
        invalid and not "".
    """
    if version_string == "":
        return Version("0")
    return Version(version_string)


def _get_bug(bug_id):
    """Fetch information about bug ``bug_id`` from https://pulp.plan.io.

    Return a ``_Bug`` instance.
    """
    # It's rarely a good idea to do type checking in a duck-typed language.
    # However, efficiency dictates we do so here. Without this type check, the
    # following will cause us to talk to the bug tracker twice and store two
    # values in the cache:
    #
    #     _get_bug(1356)
    #     _get_bug('1356')
    #
    if not isinstance(bug_id, int):
        raise TypeError(
            "Bug IDs should be integers. The given ID, {} is a {}.".format(bug_id, type(bug_id))
        )

    # Let's return the bug from the cache if possible. ¶ We shouldn't need to
    # declare a global until we want to assign to it, but waiting causes Python
    # itself to emit a SyntaxWarning.
    global _BUG_STATUS_CACHE  # pylint:disable=global-statement
    try:
        return _BUG_STATUS_CACHE[bug_id]
    except KeyError:
        pass

    # The bug is not cached. Let's fetch, cache and return it.
    async def send_request():
        async with aiohttp.ClientSession(raise_for_status=True) as session:
            async with session.get(f"https://pulp.plan.io/issues/{bug_id}.json") as response:
                return await response.json()

    bug_json = asyncio.run(send_request())

    _BUG_STATUS_CACHE[bug_id] = _Bug(
        bug_json["issue"]["status"]["name"], _convert_tpr(_get_tpr(bug_json))
    )
    return _BUG_STATUS_CACHE[bug_id]


def bug_is_fixed(bug_id, pulp_version):
    """Tell the caller whether bug ``bug_id`` should be tested.

    :param bug_id: An integer bug ID, taken from https://pulp.plan.io.
    :param pulp_version: A ``packaging.version.Version`` object telling the
        version of the Pulp server we are testing.
    :returns: ``True`` if the bug is testable, or ``False`` otherwise.
    :raises: ``TypeError`` if ``bug_id`` is not an integer.
    :raises pulp_smash.exceptions.BugStatusUnknownError: If the bug has a
        status Pulp Smash does not recognize.
    """
    try:
        bug = _get_bug(bug_id)
    except aiohttp.ClientConnectionError as err:
        message = (
            "Cannot contact the bug tracker. Pulp Smash will assume that the "
            "bug referenced is testable. Error: {}".format(err)
        )
        warnings.warn(message, RuntimeWarning)
        return True

    if isinstance(pulp_version, str):
        pulp_version = Version(pulp_version)

    if not isinstance(pulp_version, Version):
        raise TypeError(
            "Pulp version should be an instance of Version. The given"
            " Pulp version, {} is a {}.".format(pulp_version, type(pulp_version))
        )

    # bug.target_platform_release has already been verified by Version().
    if bug.status not in _TESTABLE_BUGS | _UNTESTABLE_BUGS:
        raise RuntimeError(
            "Bug {} has a status of {}. Pulp Smash only knows how to handle "
            "the following statuses: {}".format(
                bug_id, bug.status, _TESTABLE_BUGS | _UNTESTABLE_BUGS
            )
        )

    if bug.status in _TESTABLE_BUGS and bug.target_platform_release <= pulp_version:
        return True
    return False


def require(ver, exc):
    """Optionally skip a test method, based on a version string.

    This decorator concisely encapsulates a common pattern for skipping tests.
    An attribute named ``cfg`` **must** be accessible from the decorator. It
    can be used like so:

    >>> import unittest
    >>> from packaging.version import Version
    >>> from pulp_smash import config, selectors
    >>> class MyTestCase(unittest.TestCase):
    ...
    ...     @classmethod
    ...     def setUpClass(cls):
    ...         cls.cfg = config.get_config()
    ...
    ...     @selectors.require('2.7', unittest.SkipTest)
    ...     def test_foo(self):
    ...         self.assertGreaterEqual(self.cfg.pulp_version, Version('2.7'))

    If the same exception should be pased each time this method is called,
    consider using `functools.partial`_:

    >>> from functools import partial
    >>> from unittest import SkipTest
    >>> from pulp_smash.selectors import require
    >>> unittest_require = partial(require, exc=SkipTest)

    :param ver: A PEP 440 compatible version string.
    :param exc: A class to instantiate and raise as an exception. Its
        constructor must accept one string argument.

    .. _functools.partial:
        https://docs.python.org/3/library/functools.html#functools.partial
    """

    def plain_decorator(test_method):
        """Decorate function ``test_method``."""

        @wraps(test_method)
        def new_test_method(self, *args, **kwargs):
            """Wrap a (unittest test) method."""
            if self.cfg.pulp_version < Version(ver):
                raise exc(
                    """This test requires Pulp {} or later, but Pulp {} is
                    being tested. If this seems wrong, try checking the
                    settings option in the Pulp Smash configuration
                    file.""".format(
                        ver, self.cfg.pulp_version
                    )
                )
            return test_method(self, *args, **kwargs)

        return new_test_method

    return plain_decorator


def skip_if(func, var_name, result, exc):
    """Optionally skip a test method, based on a condition.

    This decorator checks to see if ``func(getattr(self, var_name))`` equals
    ``result``. If so, an exception of type ``exc`` is raised. Otherwise,
    nothing happens, and the decorated test method continues as normal. Here's
    an example of how to use this method:

    >>> import unittest
    >>> from pulp_smash.selectors import skip_if
    >>> class MyTestCase(unittest.TestCase):
    ...
    ...     @classmethod
    ...     def setUpClass(cls):
    ...         cls.my_var = False
    ...
    ...     @skip_if(bool, 'my_var', False, unittest.SkipTest)
    ...     def test_01_skips(self):
    ...         pass
    ...
    ...     def test_02_runs(self):
    ...         type(self).my_var = True
    ...
    ...     @skip_if(bool, 'my_var', False, unittest.SkipTest)
    ...     def test_03_runs(self):
    ...         pass

    If the same exception should be passed each time this method is called,
    consider using `functools.partial`_:

    >>> from functools import partial
    >>> from unittest import SkipTest
    >>> from pulp_smash.selectors import skip_if
    >>> unittest_skip_if = partial(skip_if, exc=SkipTest)

    :param var_name: A valid variable name.
    :param result: A value to compare to ``func(getattr(self, var_name))``.
    :param exc: A class to instantiate and raise as an exception. Its
        constructor must accept one string argument.

    .. _functools.partial:
        https://docs.python.org/3/library/functools.html#functools.partial
    """

    def plain_decorator(test_method):
        """Decorate function ``test_method``."""

        @wraps(test_method)
        def new_test_method(self, *args, **kwargs):
            """Wrap a (unittest test) method."""
            var_value = getattr(self, var_name)
            if func(var_value) == result:
                raise exc("{}({}) != {}".format(func, var_value, result))
            return test_method(self, *args, **kwargs)

        return new_test_method

    return plain_decorator
