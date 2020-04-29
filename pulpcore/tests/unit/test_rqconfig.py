import importlib
import os
from unittest import TestCase

from pulpcore import rqconfig
from pulpcore.app import settings


class TestRQConfig(TestCase):
    def test_env_config(self):
        """Tests that setting environment variables produces correct config for RQ."""
        os.environ["PULP_REDIS_HOST"] = "redishost"
        os.environ["PULP_REDIS_PORT"] = "1234"
        os.environ["PULP_REDIS_PASSWORD"] = "mypassword"

        # Reload settings and rqconfig so new envvars are re-read
        importlib.reload(settings)
        importlib.reload(rqconfig)

        self.assertEquals(rqconfig.REDIS_HOST, "redishost")
        self.assertEquals(rqconfig.REDIS_PORT, 1234)
        self.assertEquals(rqconfig.REDIS_PASSWORD, "mypassword")
