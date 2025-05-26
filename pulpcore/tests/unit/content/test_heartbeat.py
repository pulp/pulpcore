import pytest
from unittest.mock import call, Mock, AsyncMock

from django.db.utils import InterfaceError, OperationalError

from pulpcore.content import _heartbeat
from pulpcore.content.handler import Handler
from pulpcore.app.models import ContentAppStatus


class MockException(Exception):
    pass


@pytest.mark.parametrize("error_class", [InterfaceError, OperationalError])
@pytest.mark.asyncio
async def test_db_connection_interface_error(monkeypatch, settings, error_class):
    """
    Test that if an InterfaceError or OperationalError is raised,
    Handler._reset_db_connection() is called
    """

    mock_app_status = AsyncMock()
    mock_app_status.asave_heartbeat.side_effect = [error_class(), error_class()]
    mock_acreate = AsyncMock()
    mock_acreate.return_value = mock_app_status
    monkeypatch.setattr(ContentAppStatus.objects, "acreate", mock_acreate)
    mock_reset_db = Mock()
    monkeypatch.setattr(Handler, "_reset_db_connection", mock_reset_db)
    settings.CONTENT_APP_TTL = 1

    with pytest.raises(SystemExit):
        await _heartbeat()

    mock_app_status.asave_heartbeat.assert_called()
    mock_reset_db.assert_has_calls([call()])
