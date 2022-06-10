"""Test the status page."""
import warnings
import unittest

from django.test import override_settings
from jsonschema import validate
from pulp_smash import api, cli, config, utils
from pulp_smash.pulp3.constants import STATUS_PATH
from requests.exceptions import HTTPError

from pulpcore.tests.functional.api.utils import get_redis_status


STATUS = {
    "$schema": "http://json-schema.org/schema#",
    "title": "Pulp 3 status API schema",
    "description": ("Derived from Pulp's actual behaviour and various Pulp issues."),
    "type": "object",
    "properties": {
        "database_connection": {
            "type": "object",
            "properties": {"connected": {"type": "boolean"}},
        },
        "redis_connection": {"type": "object", "properties": {"connected": {"type": "boolean"}}},
        "missing_workers": {"type": "array", "items": {"type": "object"}},
        "online_workers": {"type": "array", "items": {"type": "object"}},
        "versions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "component": {"type": "string"},
                    "version": {"type": "string"},
                    "package": {"type": "string"},
                },
            },
        },
        "storage": {
            "type": "object",
            "properties": {
                "total": {"type": "integer"},
                "used": {"type": "integer"},
                "free": {"type": "integer"},
            },
        },
    },
}


class StatusTestCase(unittest.TestCase):
    """Tests related to the status page.

    This test explores the following issues:

    * `Pulp #2804 <https://pulp.plan.io/issues/2804>`_
    * `Pulp #2867 <https://pulp.plan.io/issues/2867>`_
    * `Pulp #3544 <https://pulp.plan.io/issues/3544>`_
    * `Pulp Smash #755 <https://github.com/pulp/pulp-smash/issues/755>`_
    """

    def setUp(self):
        """Make an API client."""
        self.client = api.Client(config.get_config(), api.json_handler)
        self.status_response = STATUS
        cli_client = cli.Client(config.get_config())
        self.storage = utils.get_pulp_setting(cli_client, "DEFAULT_FILE_STORAGE")

        if self.storage != "pulpcore.app.models.storage.FileSystem":
            self.status_response["properties"].pop("storage", None)

        self.is_redis_connected = get_redis_status()

    def test_get_authenticated(self):
        """GET the status path with valid credentials.

        Verify the response with :meth:`verify_get_response`.
        """
        self.verify_get_response(self.client.get(STATUS_PATH))

    def test_get_unauthenticated(self):
        """GET the status path with no credentials.

        Verify the response with :meth:`verify_get_response`.
        """
        del self.client.request_kwargs["auth"]
        self.verify_get_response(self.client.get(STATUS_PATH))

    def test_post_authenticated(self):
        """POST the status path with valid credentials.

        Assert an error is returned.
        """
        with self.assertRaises(HTTPError):
            self.client.post(STATUS_PATH)

    def verify_get_response(self, status):
        """Verify the response to an HTTP GET call.

        Verify that several attributes and have the correct type or value.
        """
        validate(status, self.status_response)
        self.assertTrue(status["database_connection"]["connected"])
        self.assertNotEqual(status["online_workers"], [])
        self.assertNotEqual(status["versions"], [])
        if self.storage == "pulpcore.app.models.storage.FileSystem":
            self.assertIsNotNone(status["storage"])
        else:
            self.assertIsNone(status["storage"])

        self.assertIsNotNone(status["redis_connection"])
        if self.is_redis_connected:
            self.assertTrue(status["redis_connection"]["connected"])
        else:
            warnings.warn("Could not connect to the Redis server")

    @override_settings(CACHE_ENABLED=False)
    def verify_get_response_without_redis(self, status):
        """Verify the response to an HTTP GET call when Redis is not used.

        Verify that redis_connection is null
        """
        validate(status, self.status_response)
        self.assertIsNone(status["redis_connection"])
