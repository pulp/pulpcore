"""Test related to the api docs page."""
import unittest

from pulp_smash import api, config
from pulp_smash.pulp3.constants import API_DOCS_PATH
from requests.exceptions import HTTPError


class ApiDocsTestCase(unittest.TestCase):
    """Test whether API auto generated docs are available.

    This test targets the following issue:

    * `Pulp Smash #893 <https://github.com/pulp/pulp-smash/issues/893>`_
    """

    def setUp(self):
        """Create an API Client."""
        cfg = config.get_config()
        self.client = api.Client(cfg)

    def test_valid_credentials(self):
        """Get API documentation with valid credentials.

        Assert the API documentation is returned.
        """
        self.client.get(API_DOCS_PATH)

    def test_no_credentials(self):
        """Get API documentation with no credentials.

        Assert the API documentation is returned.
        """
        del self.client.request_kwargs["auth"]
        self.client.get(API_DOCS_PATH)

    def test_http_method(self):
        """Get API documentation with an HTTP method other than GET.

        Assert an error is returned.
        """
        with self.assertRaises(HTTPError):
            self.client.post(API_DOCS_PATH)
