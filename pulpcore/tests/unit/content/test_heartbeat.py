import pytest
from unittest.mock import call, Mock, AsyncMock

from django.db.utils import InterfaceError, OperationalError

from pulpcore.content import _heartbeat
from pulpcore.content.handler import Handler
from pulpcore.app.models import ContentAppStatus


class MockException(Exception):
    pass


@pytest.mark.asyncio
async def test_db_connection_interface_error(monkeypatch, settings):
    """
    Test that if an InterfaceError or OperationalError is raised,
    Handler._reset_db_connection() is called
    """

    mock_aget_or_create = AsyncMock()
    mock_aget_or_create.side_effect = [InterfaceError(), OperationalError(), MockException()]
    monkeypatch.setattr(ContentAppStatus.objects, "aget_or_create", mock_aget_or_create)
    mock_reset_db = Mock()
    monkeypatch.setattr(Handler, "_reset_db_connection", mock_reset_db)
    settings.CONTENT_APP_TTL = 1

    with pytest.raises(MockException):
        await _heartbeat()

    mock_aget_or_create.assert_called()
    mock_reset_db.assert_has_calls([call(), call()])
