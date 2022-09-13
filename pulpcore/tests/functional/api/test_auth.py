"""Tests for Pulp 3's authentication API.

For more information, see the documentation on `Authentication
<https://docs.pulpproject.org/restapi.html#section/Authentication>`_.
"""
import unittest

from aiohttp.client import BasicAuth
from aiohttp.client_exceptions import ClientResponseError

from pulpcore.tests.suite import api, config, utils
from pulpcore.tests.suite.constants import ARTIFACTS_PATH


class AuthTestCase(unittest.TestCase):
    """Test Pulp3 Authentication."""

    def setUp(self):
        """Set common variable."""
        self.cfg = config.get_config()

    def test_base_auth_success(self):
        """Perform HTTP basic authentication with valid credentials.

        Assert that a response indicating success is returned.

        Assertion is made by the response_handler.
        """
        api.Client(self.cfg, api.json_handler).get(
            ARTIFACTS_PATH, auth=BasicAuth(*self.cfg.pulp_auth)
        )

    def test_base_auth_failure(self):
        """Perform HTTP basic authentication with invalid credentials.

        Assert that a response indicating failure is returned.
        """
        self.cfg.pulp_auth[1] = utils.uuid4()  # randomize password
        response = api.Client(self.cfg, api.echo_handler).get(
            ARTIFACTS_PATH, auth=BasicAuth(*self.cfg.pulp_auth)
        )
        with self.assertRaises(ClientResponseError) as cm:
            response.raise_for_status()

        message = cm.exception.message.text
        for key in ("invalid", "username", "password"):
            self.assertIn(key, message.lower(), message)
