"""Tests for the core_ca_relpath_pattern_idx migration helpers."""

import importlib
from types import SimpleNamespace

import pytest
from django.db import connection

migration = importlib.import_module(
    "pulpcore.app.migrations.0162_contentartifact_relative_path_pattern_index"
)

INDEX = "core_ca_relpath_pattern_idx"
schema_editor = SimpleNamespace(connection=connection)


def index_info():
    with connection.cursor() as cursor:
        return migration._index_info(cursor)


def replace_index(create_sql, comment=None):
    with connection.cursor() as cursor:
        cursor.execute(f'DROP INDEX IF EXISTS "{INDEX}"')
        cursor.execute(create_sql)
        if comment:
            cursor.execute(f"COMMENT ON INDEX \"{INDEX}\" IS '{comment}'")


@pytest.mark.django_db
def test_equivalent_existing_index_is_reused():
    # The index exists with the expected definition because the test database ran the migration.
    before = index_info()
    assert migration._EXPECTED_INDEX_DEF.match(before[2])

    migration.create_relative_path_index(None, schema_editor)

    assert index_info() == before


@pytest.mark.django_db
@pytest.mark.parametrize(
    "create_sql",
    [
        # Default operator class instead of text_pattern_ops.
        f'CREATE INDEX "{INDEX}" ON core_contentartifact (relative_path)',
        # Wrong column.
        f'CREATE INDEX "{INDEX}" ON core_contentartifact (relative_path text_pattern_ops, content_id)',
        # Partial index.
        f'CREATE INDEX "{INDEX}" ON core_contentartifact (relative_path text_pattern_ops)'
        " WHERE relative_path <> ''",
    ],
    ids=["default-opclass", "extra-column", "partial"],
)
def test_index_with_unexpected_definition_is_rejected(create_sql):
    replace_index(create_sql)
    before = index_info()

    with pytest.raises(RuntimeError, match="unexpected definition"):
        migration.create_relative_path_index(None, schema_editor)

    # The mismatching index is left in place, not dropped or replaced.
    assert index_info() == before


@pytest.mark.django_db
def test_reverse_leaves_index_it_did_not_create():
    replace_index(
        f'CREATE INDEX "{INDEX}" ON core_contentartifact USING btree'
        " (relative_path text_pattern_ops)",
        comment="created-elsewhere",
    )

    migration.create_relative_path_index(None, schema_editor)
    migration.drop_relative_path_index(None, schema_editor)

    assert index_info() is not None


class RecordingCursor:
    """A stand-in cursor that returns one canned index row and records every statement."""

    def __init__(self, row):
        self.row = row
        self.statements = []

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False

    def execute(self, sql, params=None):
        self.statements.append(sql)

    def fetchone(self):
        return self.row


def test_unique_index_is_rejected_without_running_ddl():
    """
    A UNIQUE index of the same name is rejected and left alone.

    It cannot be created in the test database, where relative_path values are not unique, so the
    existing index is simulated instead of built.
    """
    definition = (
        f"CREATE UNIQUE INDEX {INDEX} ON public.core_contentartifact "
        "USING btree (relative_path text_pattern_ops)"
    )
    cursor = RecordingCursor((True, None, definition))
    fake_editor = SimpleNamespace(connection=SimpleNamespace(cursor=lambda: cursor))

    with pytest.raises(RuntimeError, match="unexpected definition"):
        migration.create_relative_path_index(None, fake_editor)

    # Only the lookup ran: nothing was created, commented on, or dropped.
    assert len(cursor.statements) == 1
    assert cursor.statements[0].lstrip().startswith("SELECT")
