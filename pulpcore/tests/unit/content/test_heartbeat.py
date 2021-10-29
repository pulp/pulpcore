import asyncio
from unittest import skip
from unittest.mock import patch, call

from django.db.utils import InterfaceError, OperationalError
from django.test import TestCase

from pulpcore.content import _heartbeat


class ContentHeartbeatTestCase(TestCase):
    @skip("Skipping while resolving https://github.com/rochacbruno/dynaconf/issues/689")
    @patch("pulpcore.app.models.ContentAppStatus.objects.get_or_create")
    @patch("pulpcore.content.handler.Handler._reset_db_connection")
    def test_db_connection_interface_error(self, mock_reset_db, mock_get_or_create):
        """
        Test that if an InterfaceError or OperationalError is raised,
        Handler._reset_db_connection() is called
        """

        class MockException(Exception):
            pass

        mock_get_or_create.side_effect = [InterfaceError(), OperationalError(), MockException()]

        loop = asyncio.get_event_loop()
        with self.settings(CONTENT_APP_TTL=1):
            try:
                loop.run_until_complete(_heartbeat())
            except MockException:
                pass
        loop.close()

        mock_get_or_create.assert_called()
        mock_reset_db.assert_has_calls([call(), call()])
