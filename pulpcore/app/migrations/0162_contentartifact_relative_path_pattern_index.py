import re

import django.contrib.postgres.indexes
from django.db import migrations, models

_INDEX_NAME = "core_ca_relpath_pattern_idx"
_INDEX_MARKER = "pulpcore:0162:core_ca_relpath_pattern_idx"
_CREATE_INDEX_SQL = (
    'CREATE INDEX CONCURRENTLY IF NOT EXISTS "core_ca_relpath_pattern_idx" '
    'ON "core_contentartifact" USING btree ("relative_path" text_pattern_ops)'
)
_DROP_INDEX_SQL = 'DROP INDEX CONCURRENTLY IF EXISTS "core_ca_relpath_pattern_idx"'
# pg_get_indexdef output for the expected index, e.g.
# CREATE INDEX core_ca_relpath_pattern_idx ON public.core_contentartifact USING btree
# (relative_path text_pattern_ops)
_EXPECTED_INDEX_DEF = re.compile(
    r'^CREATE INDEX "?core_ca_relpath_pattern_idx"? ON (?:"?\w+"?\.)?"?core_contentartifact"? '
    r'USING btree \("?relative_path"? text_pattern_ops\)$'
)
_COMMENT_INDEX_SQL = (
    'COMMENT ON INDEX "core_ca_relpath_pattern_idx" '
    "IS 'pulpcore:0162:core_ca_relpath_pattern_idx'"
)


def _index_info(cursor):
    cursor.execute(
        """
        SELECT
            pg_index.indisvalid,
            obj_description(indexrel.oid, 'pg_class'),
            pg_get_indexdef(indexrel.oid)
        FROM pg_class AS indexrel
        JOIN pg_index ON pg_index.indexrelid = indexrel.oid
        JOIN pg_namespace AS namespace ON namespace.oid = indexrel.relnamespace
        WHERE indexrel.relname = %s AND namespace.nspname = current_schema()
        """,
        [_INDEX_NAME],
    )
    return cursor.fetchone()


def create_relative_path_index(apps, schema_editor):
    """Create the index, reusing an equivalent one that already exists (e.g. created out of band)."""
    with schema_editor.connection.cursor() as cursor:
        info = _index_info(cursor)
        if info:
            valid, _, definition = info
            if not valid:
                raise RuntimeError(
                    f"Index {_INDEX_NAME!r} exists but is invalid; refusing to drop it automatically."
                )
            if not _EXPECTED_INDEX_DEF.match(definition):
                raise RuntimeError(
                    f"Index {_INDEX_NAME!r} exists with an unexpected definition ({definition!r}); "
                    "refusing to reuse or drop it automatically."
                )
            return

        # IF NOT EXISTS keeps concurrent migration runs from creating a second physical index.
        cursor.execute(_CREATE_INDEX_SQL)
        # The comment records ownership so the reverse migration only drops what it created.
        cursor.execute(_COMMENT_INDEX_SQL)


def drop_relative_path_index(apps, schema_editor):
    """Drop only an index created by this migration, leaving pre-existing ones intact."""
    with schema_editor.connection.cursor() as cursor:
        info = _index_info(cursor)
        if info and info[1] == _INDEX_MARKER:
            cursor.execute(_DROP_INDEX_SQL)


class Migration(migrations.Migration):
    """Add the index used by the content handler's relative_path prefix and equality lookups."""

    atomic = False  # CREATE/DROP INDEX CONCURRENTLY cannot run in a transaction.

    dependencies = [
        ("core", "0161_upstreampulp_remote_policy"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.AddIndex(
                    model_name="contentartifact",
                    index=models.Index(
                        django.contrib.postgres.indexes.OpClass(
                            "relative_path", name="text_pattern_ops"
                        ),
                        name=_INDEX_NAME,
                    ),
                ),
            ],
            database_operations=[
                migrations.RunPython(create_relative_path_index, drop_relative_path_index),
            ],
        ),
    ]
