# coding=utf-8
"""Utilities for Pulpcore tests."""
from functools import partial
from unittest import SkipTest

from pulp_smash import config, selectors
from pulp_smash.pulp3.utils import require_pulp_3, require_pulp_plugins

from pulpcore.client.pulpcore import ApiClient


def set_up_module():
    """Skip tests Pulp 3 isn't under test or if pulpcore isn't installed."""
    require_pulp_3(SkipTest)
    require_pulp_plugins({"pulpcore"}, SkipTest)


skip_if = partial(selectors.skip_if, exc=SkipTest)  # pylint:disable=invalid-name
"""The ``@skip_if`` decorator, customized for unittest.

:func:`pulp_smash.selectors.skip_if` is test runner agnostic. This function is
identical, except that ``exc`` has been set to ``unittest.SkipTest``.
"""

cfg = config.get_config()
configuration = cfg.get_bindings_config()
core_client = ApiClient(configuration)
