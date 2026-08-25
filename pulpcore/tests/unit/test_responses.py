import os
from datetime import datetime, timezone

import pytest
from aiohttp.test_utils import make_mocked_request
from aiohttp.web import FileResponse
from django.utils.http import http_date

from pulpcore.responses import PulpFileResponse

# _make_response / _FileResponseResult exist only on aiohttp 3.11+. Lowerbounds installs 3.10.
_SKIP_MAKE_RESPONSE = pytest.mark.skipif(
    not hasattr(FileResponse, "_make_response"),
    reason="aiohttp FileResponse._make_response requires aiohttp 3.11+",
)

_PULP_LM = http_date(datetime(2024, 6, 1, tzinfo=timezone.utc).timestamp())
# 2001-09-09; If-Modified-Since between this and _PULP_LM is the interesting case
_FILE_MTIME = 1_000_000_000
_IF_MODIFIED_SINCE_AFTER_MTIME = http_date(datetime(2022, 1, 1, tzinfo=timezone.utc).timestamp())


def _artifact(tmp_path):
    path = tmp_path / "artifact"
    path.write_bytes(b"payload")
    os.utime(path, (_FILE_MTIME, _FILE_MTIME))
    return path


@pytest.mark.parametrize("with_handler_lm", [True, False], ids=["handler-lm", "no-lm"])
def test_pulp_file_response_ignores_file_mtime(tmp_path, with_handler_lm):
    """aiohttp's file-mtime assignment must not advertise a filesystem Last-Modified."""
    headers = {"Last-Modified": _PULP_LM} if with_handler_lm else None
    response = PulpFileResponse(_artifact(tmp_path), headers=headers)
    response.last_modified = 2_000_000_000
    if with_handler_lm:
        assert response.headers["Last-Modified"] == _PULP_LM
    else:
        assert "Last-Modified" not in response.headers


@pytest.mark.parametrize("with_handler_lm", [True, False], ids=["handler-lm", "no-lm"])
def test_pulp_file_response_never_emits_mtime_etag(tmp_path, with_handler_lm):
    """mtime ETags are not advertised, with or without a Pulp Last-Modified."""
    headers = {"Last-Modified": _PULP_LM} if with_handler_lm else None
    response = PulpFileResponse(_artifact(tmp_path), headers=headers)
    response.etag = "abc123"
    assert "ETag" not in response.headers


@_SKIP_MAKE_RESPONSE
@pytest.mark.parametrize("with_handler_lm", [True, False], ids=["handler-lm", "no-lm"])
def test_pulp_file_response_does_not_304_on_file_mtime(tmp_path, with_handler_lm):
    """If-Modified-Since after file mtime must not 304; stock FileResponse would."""
    from aiohttp.web_fileresponse import _FileResponseResult

    path = _artifact(tmp_path)
    headers = {"Last-Modified": _PULP_LM} if with_handler_lm else None
    request = make_mocked_request(
        "GET", "/", headers={"If-Modified-Since": _IF_MODIFIED_SINCE_AFTER_MTIME}
    )

    pulp = PulpFileResponse(str(path), headers=headers)
    result, fobj, _st, _enc = pulp._make_response(request, "")
    try:
        assert result is _FileResponseResult.SEND_FILE
    finally:
        if fobj:
            fobj.close()
    if with_handler_lm:
        assert pulp.headers["Last-Modified"] == _PULP_LM
    else:
        assert "Last-Modified" not in pulp.headers

    stock = FileResponse(str(path))
    result, fobj, _st, _enc = stock._make_response(
        make_mocked_request(
            "GET", "/", headers={"If-Modified-Since": _IF_MODIFIED_SINCE_AFTER_MTIME}
        ),
        "",
    )
    try:
        assert result is _FileResponseResult.NOT_MODIFIED
    finally:
        if fobj:
            fobj.close()


@_SKIP_MAKE_RESPONSE
def test_pulp_file_response_does_not_blank_if_range(tmp_path):
    """If-Range stays available so aiohttp can refuse a stale Range instead of a corrupt 206."""
    from aiohttp.web_fileresponse import _FileResponseResult

    if_range = http_date(_FILE_MTIME)
    request = make_mocked_request(
        "GET",
        "/",
        headers={
            "If-Range": if_range,
            "Range": "bytes=0-1",
            "If-Modified-Since": if_range,
        },
    )
    response = PulpFileResponse(str(_artifact(tmp_path)), headers={"Last-Modified": _PULP_LM})
    result, fobj, _st, _enc = response._make_response(request, "")
    try:
        assert result is _FileResponseResult.SEND_FILE
    finally:
        if fobj:
            fobj.close()

    assert request.if_range is not None
    assert request.if_modified_since is None
