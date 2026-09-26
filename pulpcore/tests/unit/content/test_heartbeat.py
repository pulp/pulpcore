from unittest.mock import AsyncMock, Mock, call, patch

import pytest
from django.db.utils import InternalError, InterfaceError, OperationalError

from pulpcore.app.models.status import AppStatus, AppStatusManager
from pulpcore.content import _heartbeat
from pulpcore.content.handler import Handler


class MockException(Exception):
    pass


def _make_read_only_error():
    cause = Exception("cannot execute UPDATE in a read-only transaction")
    cause.pgcode = "25006"
    exc = InternalError("read-only")
    exc.__cause__ = cause
    return exc


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
    monkeypatch.setattr(AppStatusManager, "acreate", mock_acreate)
    monkeypatch.setattr(AppStatus, "objects", AppStatusManager())
    mock_reset_db = Mock()
    monkeypatch.setattr(Handler, "_reset_db_connection", mock_reset_db)
    settings.CONTENT_APP_TTL = 1

    with pytest.raises(SystemExit):
        await _heartbeat()

    mock_app_status.asave_heartbeat.assert_called()
    mock_reset_db.assert_has_calls([call()])


@pytest.mark.asyncio
async def test_read_only_heartbeat_skips_without_exit(monkeypatch, settings):
    """
    When the DB is read-only, heartbeat should skip without exiting.
    """
    read_only_exc = _make_read_only_error()

    mock_app_status = AsyncMock()
    mock_app_status.asave_heartbeat.side_effect = [read_only_exc, read_only_exc]
    mock_acreate = AsyncMock()
    mock_acreate.return_value = mock_app_status
    monkeypatch.setattr(AppStatusManager, "acreate", mock_acreate)
    monkeypatch.setattr(AppStatus, "objects", AppStatusManager())
    mock_reset_db = Mock()
    monkeypatch.setattr(Handler, "_reset_db_connection", mock_reset_db)
    settings.CONTENT_APP_TTL = 1

    iteration_count = 0

    original_sleep = __import__("asyncio").sleep

    async def counting_sleep(seconds):
        nonlocal iteration_count
        iteration_count += 1
        if iteration_count >= 2:
            raise KeyboardInterrupt("stop test loop")
        await original_sleep(0)

    with patch("asyncio.sleep", side_effect=counting_sleep):
        with pytest.raises(KeyboardInterrupt):
            await _heartbeat()

    mock_app_status.asave_heartbeat.assert_called()
    mock_reset_db.assert_called()


@pytest.mark.asyncio
async def test_read_only_acreate_skips_without_exit(monkeypatch, settings):
    """
    When acreate fails with read-only, _heartbeat should not exit.
    """
    read_only_exc = _make_read_only_error()

    mock_acreate = AsyncMock(side_effect=read_only_exc)
    monkeypatch.setattr(AppStatusManager, "acreate", mock_acreate)
    monkeypatch.setattr(AppStatus, "objects", AppStatusManager())
    mock_reset_db = Mock()
    monkeypatch.setattr(Handler, "_reset_db_connection", mock_reset_db)
    settings.CONTENT_APP_TTL = 1

    iteration_count = 0

    async def counting_sleep(seconds):
        nonlocal iteration_count
        iteration_count += 1
        if iteration_count >= 2:
            raise KeyboardInterrupt("stop test loop")

    with patch("asyncio.sleep", side_effect=counting_sleep):
        with pytest.raises(KeyboardInterrupt):
            await _heartbeat()

    assert mock_acreate.call_count >= 2
