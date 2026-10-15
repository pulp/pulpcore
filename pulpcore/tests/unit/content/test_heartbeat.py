from unittest.mock import AsyncMock, Mock

import pytest
from django.db.utils import IntegrityError, InterfaceError, OperationalError
from gunicorn.arbiter import Arbiter

from pulpcore.app.models.status import AppStatus, AppStatusManager
from pulpcore.content import _heartbeat
from pulpcore.content.handler import Handler


class MockException(Exception):
    pass


@pytest.mark.parametrize("error_class", [InterfaceError, OperationalError])
@pytest.mark.asyncio
async def test_exits_on_heartbeat_database_failure(monkeypatch, settings, error_class):
    mock_app_status = AsyncMock()
    mock_app_status.asave_heartbeat.side_effect = [error_class(), error_class()]
    mock_acreate = AsyncMock()
    mock_acreate.return_value = mock_app_status
    monkeypatch.setattr(AppStatusManager, "acreate", mock_acreate)
    monkeypatch.setattr(AppStatus, "objects", AppStatusManager())
    mock_reset_db = Mock()
    monkeypatch.setattr(Handler, "_reset_db_connection", mock_reset_db)
    mock_exit = Mock(side_effect=SystemExit(Arbiter.WORKER_BOOT_ERROR))
    monkeypatch.setattr("pulpcore.content.os._exit", mock_exit)
    settings.CONTENT_APP_TTL = 1
    monkeypatch.setattr("pulpcore.content.asyncio.sleep", AsyncMock(return_value=None))

    with pytest.raises(SystemExit) as exc:
        await _heartbeat()

    assert exc.value.code == Arbiter.WORKER_BOOT_ERROR
    assert mock_app_status.asave_heartbeat.await_count == 2
    mock_reset_db.assert_called_once_with()
    mock_exit.assert_called_once_with(Arbiter.WORKER_BOOT_ERROR)


@pytest.mark.asyncio
@pytest.mark.parametrize("error_class", [IntegrityError, OperationalError])
async def test_exits_on_initial_registration_database_failure(monkeypatch, settings, error_class):
    mock_acreate = AsyncMock(side_effect=error_class())
    monkeypatch.setattr(AppStatusManager, "acreate", mock_acreate)
    monkeypatch.setattr(AppStatus, "objects", AppStatusManager())
    mock_exit = Mock(side_effect=SystemExit(Arbiter.WORKER_BOOT_ERROR))
    monkeypatch.setattr("pulpcore.content.os._exit", mock_exit)

    with pytest.raises(SystemExit) as exc:
        await _heartbeat()

    assert exc.value.code == Arbiter.WORKER_BOOT_ERROR
    mock_exit.assert_called_once_with(Arbiter.WORKER_BOOT_ERROR)
    assert mock_acreate.await_count == 1
