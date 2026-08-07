from unittest.mock import MagicMock, patch

import pytest
from django.db.utils import DatabaseError, InternalError

from pulpcore.app.entrypoint import PulpApiWorker

_mock_connection = patch("pulpcore.app.entrypoint.connection")


def _make_read_only_error():
    cause = Exception("cannot execute UPDATE in a read-only transaction")
    cause.pgcode = "25006"
    exc = InternalError("read-only")
    exc.__cause__ = cause
    return exc


def _make_worker():
    with patch.object(PulpApiWorker, "__init__", lambda self, *a, **kw: None):
        worker = PulpApiWorker()
    worker.name = "test-worker@host"
    worker.versions = {"core": "3.115.0"}
    worker.app_status = MagicMock()
    worker.beat_msg = "heartbeat ok"
    worker.fail_beat_msg = "heartbeat failed"
    return worker


@_mock_connection
class TestHeartbeatReadOnly:
    def test_heartbeat_skips_on_read_only(self, _conn):
        worker = _make_worker()
        read_only_exc = _make_read_only_error()
        worker.app_status.save_heartbeat.side_effect = [read_only_exc, read_only_exc]

        worker.heartbeat()

        assert worker.app_status.save_heartbeat.call_count == 2

    def test_heartbeat_raises_on_real_db_error(self, _conn):
        worker = _make_worker()
        db_error = DatabaseError("connection lost")
        worker.app_status.save_heartbeat.side_effect = [db_error, db_error]

        with pytest.raises(DatabaseError):
            worker.heartbeat()

    def test_heartbeat_retries_create_when_app_status_none(self, _conn):
        worker = _make_worker()
        worker.app_status = None
        read_only_exc = _make_read_only_error()

        with patch("pulpcore.app.models.AppStatus") as mock_cls:
            mock_cls.objects.create.side_effect = read_only_exc
            worker.heartbeat()

        assert worker.app_status is None

    def test_heartbeat_creates_app_status_when_db_recovers(self, _conn):
        worker = _make_worker()
        worker.app_status = None
        mock_status = MagicMock()

        with patch("pulpcore.app.models.AppStatus") as mock_cls:
            mock_cls.objects.create.return_value = mock_status
            worker.heartbeat()

        assert worker.app_status is mock_status
        mock_status.save_heartbeat.assert_called_once()


class TestRunCleanup:
    def test_run_finally_tolerates_db_error(self):
        worker = _make_worker()
        worker.app_status.delete.side_effect = DatabaseError("read-only")

        with patch.object(PulpApiWorker.__bases__[0], "run"):
            worker.run()

        worker.app_status.delete.assert_called_once()

    def test_run_finally_skips_when_no_app_status(self):
        worker = _make_worker()
        worker.app_status = None

        with patch.object(PulpApiWorker.__bases__[0], "run"):
            worker.run()
