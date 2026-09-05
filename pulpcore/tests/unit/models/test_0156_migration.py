"""Unit tests for migration 0156's normalize helper and migration function."""

import importlib
from unittest.mock import MagicMock, call, patch

import pytest

_migration = importlib.import_module(
    "pulpcore.app.migrations.0156_alter_contentartifact_relative_path_and_more"
)
_normalize_path = _migration._normalize_path
fix_base_path_violations = _migration.fix_base_path_violations


# ---------------------------------------------------------------------------
# _normalize_path — pure Python, no database required
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "value, expected",
    [
        # trailing slash is stripped
        ("fedora/", "fedora"),
        # leading slash is stripped
        ("/fedora", "fedora"),
        # double slash is collapsed
        ("fedora//el9", "fedora/el9"),
        # newline is removed
        ("fedora\nel9", "fedorael9"),
        # space is removed
        ("fedora el9", "fedorael9"),
        # query string is stripped
        ("fedora?foo=1", "fedora"),
        # fragment is stripped
        ("fedora#anchor", "fedora"),
        # dot component is removed
        ("fedora/./el9", "fedora/el9"),
        # dotdot component is collapsed
        ("fedora/../el9", "el9"),
        # clean path is returned unchanged
        ("fedora/el9/x86_64", "fedora/el9/x86_64"),
    ],
)
def test_normalize_path(value, expected):
    assert _normalize_path(value) == expected


# ---------------------------------------------------------------------------
# fix_base_path_violations — mock the DB cursor to avoid constraint conflicts
# ---------------------------------------------------------------------------


def _make_cursor(rows):
    """Return a context-manager mock cursor that yields *rows* on fetchall()."""
    cursor = MagicMock()
    cursor.__enter__ = lambda s: s
    cursor.__exit__ = MagicMock(return_value=False)
    cursor.fetchall.return_value = rows
    return cursor


def test_fix_base_path_violations_normalizes_row(monkeypatch):
    """A row with a trailing-slash base_path is UPDATE-d to the normalized value."""
    pk = "some-uuid"
    bad_path = "trailing/"
    good_path = "trailing"

    select_cursor = _make_cursor([(pk, bad_path)])
    update_cursor = _make_cursor([])

    cursors = iter([select_cursor, update_cursor])
    connection_mock = MagicMock()
    connection_mock.cursor.side_effect = lambda: next(cursors)

    with patch("pulpcore.app.migrations.0156_alter_contentartifact_relative_path_and_more.connection", connection_mock):
        fix_base_path_violations(None, None)

    update_cursor.execute.assert_called_once_with(
        "UPDATE core_distribution SET base_path = %s WHERE pulp_id = %s",
        [good_path, pk],
    )


def test_fix_base_path_violations_skips_clean_rows(monkeypatch):
    """A row with a valid base_path is NOT UPDATE-d."""
    pk = "some-uuid"
    clean_path = "fedora/el9"

    # SELECT returns no rows (clean_path doesn't match the invalid regex)
    select_cursor = _make_cursor([])
    connection_mock = MagicMock()
    connection_mock.cursor.return_value = select_cursor

    with patch("pulpcore.app.migrations.0156_alter_contentartifact_relative_path_and_more.connection", connection_mock):
        fix_base_path_violations(None, None)

    # Only one cursor call (the SELECT), no UPDATE
    assert connection_mock.cursor.call_count == 1


def test_fix_base_path_violations_raises_for_unfixable_path():
    """A row whose path normalizes to empty string raises RuntimeError."""
    pk = "some-uuid"
    # A bare "." normalizes to "" which is unfixable
    unfixable_path = "."

    select_cursor = _make_cursor([(pk, unfixable_path)])
    connection_mock = MagicMock()
    connection_mock.cursor.return_value = select_cursor

    with patch("pulpcore.app.migrations.0156_alter_contentartifact_relative_path_and_more.connection", connection_mock):
        with pytest.raises(RuntimeError, match="could not be automatically normalized"):
            fix_base_path_violations(None, None)
