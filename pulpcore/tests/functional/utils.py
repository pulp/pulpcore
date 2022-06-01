"""Utilities for Pulpcore tests."""
import aiohttp

from functools import partial
from unittest import SkipTest

from pulp_smash import config, selectors

from pulpcore.client.pulpcore import ApiClient


async def get_response(url):
    async with aiohttp.ClientSession() as session:
        return await session.get(url)


skip_if = partial(selectors.skip_if, exc=SkipTest)  # pylint:disable=invalid-name
"""The ``@skip_if`` decorator, customized for unittest.

:func:`pulp_smash.selectors.skip_if` is test runner agnostic. This function is
identical, except that ``exc`` has been set to ``unittest.SkipTest``.
"""

cfg = config.get_config()
configuration = cfg.get_bindings_config()
core_client = ApiClient(configuration)
