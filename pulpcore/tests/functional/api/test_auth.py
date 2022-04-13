"""Tests for Pulp 3's authentication API.

For more information, see the documentation on `Authentication
<https://docs.pulpproject.org/restapi.html#section/Authentication>`_.
"""
import unittest

from pulp_smash import api, config, utils
from pulp_smash.pulp3.constants import ARTIFACTS_PATH
from requests.auth import HTTPBasicAuth
from requests.exceptions import HTTPError


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
            ARTIFACTS_PATH, auth=HTTPBasicAuth(*self.cfg.pulp_auth)
        )

    def test_base_auth_failure(self):
        """Perform HTTP basic authentication with invalid credentials.

        Assert that a response indicating failure is returned.
        """
        self.cfg.pulp_auth[1] = utils.uuid4()  # randomize password
        response = api.Client(self.cfg, api.echo_handler).get(
            ARTIFACTS_PATH, auth=HTTPBasicAuth(*self.cfg.pulp_auth)
        )
        with self.assertRaises(HTTPError):
            response.raise_for_status()
        for key in ("invalid", "username", "password"):
            self.assertIn(key, response.json()["detail"].lower(), response.json())
