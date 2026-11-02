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
        # Unique index.
        f'CREATE UNIQUE INDEX "{INDEX}" ON core_contentartifact (relative_path text_pattern_ops)',
    ],
    ids=["default-opclass", "extra-column", "partial", "unique"],
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
