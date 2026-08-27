import importlib
from types import SimpleNamespace
from uuid import uuid4

import pytest
from django.apps import apps
from django.db import connection

from pulpcore.app.models import RepositoryVersion
from pulpcore.plugin.models import Content, Repository

populate_content_ids = importlib.import_module(
    "pulpcore.app.migrations.0152_alter_repositoryversion_content_ids"
).populate_content_ids


def _run_populate():
    schema_editor = SimpleNamespace(
        connection=connection,
        quote_name=connection.ops.quote_name,
    )
    populate_content_ids(apps, schema_editor)


def _membership_ids(version):
    return set(version._content_relationships().values_list("content_id", flat=True))


@pytest.fixture
def repository(db):
    repository = Repository.objects.create(name=uuid4())
    repository.CONTENT_TYPES = [Content]
    return repository


def test_populate_content_ids_from_content_relationships(repository):
    contents = [Content(pulp_type="core.content") for _ in range(4)]
    Content.objects.bulk_create(contents)
    pks = [c.pk for c in contents]

    version0 = repository.latest_version()
    with repository.new_version() as version1:
        version1.add_content(Content.objects.filter(pk__in=pks[:3]))
    with repository.new_version() as version2:
        version2.remove_content(Content.objects.filter(pk__in=pks[:1]))
    with repository.new_version() as version3:
        version3.add_content(Content.objects.filter(pk__in=pks[3:]))

    # A second repository whose cache is already populated must be left alone.
    other = Repository.objects.create(name=uuid4())
    other.CONTENT_TYPES = [Content]
    with other.new_version() as other_v1:
        other_v1.add_content(Content.objects.filter(pk__in=pks[:2]))
    other_v1.refresh_from_db()
    other_ids_before = list(other_v1.content_ids)

    rv_table = connection.ops.quote_name(RepositoryVersion._meta.db_table)
    with connection.cursor() as cursor:
        # Flush deferred triggers from the version inserts so ALTER TABLE can run
        # inside the test transaction.
        cursor.execute("SET CONSTRAINTS ALL IMMEDIATE")
        cursor.execute(f"ALTER TABLE {rv_table} ALTER COLUMN content_ids DROP NOT NULL")
        # Leave version3 populated (the post-3.83 case) and null the older versions.
        cursor.execute(
            f"UPDATE {rv_table} SET content_ids = NULL WHERE repository_id = %s AND number < %s",
            [repository.pk, version3.number],
        )

    _run_populate()

    for version in (version0, version1, version2, version3):
        version.refresh_from_db()
        assert version.content_ids is not None
        assert set(version.content_ids) == _membership_ids(version)

    other_v1.refresh_from_db()
    assert list(other_v1.content_ids) == other_ids_before
