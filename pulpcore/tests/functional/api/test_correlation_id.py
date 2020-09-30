import unittest
import uuid

from pulp_smash import api, cli, config
from pulp_smash.pulp3.bindings import monitor_task

from pulpcore.client.pulpcore import ApiClient, OrphansApi, TasksApi


class CorrelationIdTestCase(unittest.TestCase):
    """Test correlation id functionality."""

    @classmethod
    def setUpClass(cls):
        """Set up class variables."""
        cls.cid = str(uuid.uuid4())
        cls.cfg = config.get_config()
        cls.client = api.Client(cls.cfg, api.json_handler)
        cls.client = ApiClient(
            configuration=cls.cfg.get_bindings_config(),
            header_name="Correlation-ID",
            header_value=cls.cid,
        )
        cls.cli_client = cli.Client(cls.cfg)

        cls.orphan_api = OrphansApi(cls.client)
        cls.task_api = TasksApi(cls.client)

    def test_correlation_id(self):
        """Test that a correlation can be passed as a header and logged."""
        response, status, headers = self.orphan_api.delete_with_http_info()
        monitor_task(response.task)
        task = self.task_api.read(response.task)
        self.assertEqual(headers["Correlation-ID"], self.cid)
        self.assertEqual(task.logging_cid, self.cid)
