"""
Regression test: transaction.on_commit() defaults to queuing its callback against the 'default'
alias's commit -- it never consults the db_router. Artifact.delete()'s file-deletion callback
(and Repository's old-version/checkpoint cleanup callbacks) didn't pass using=, so they always
queued on 'default' regardless of which alias the actual transaction was on. For a satellite
transaction, that meant the callback could fire immediately (if 'default' had no open
transaction to wait on) independent of whether the satellite transaction itself committed or
rolled back -- observed as a rollback that restored the Artifact row while its file was already
deleted.
"""

import hashlib
import uuid

import pytest
from django.core.files.base import ContentFile
from django.test import TestCase

from pulpcore.app.contexts import with_domain
from pulpcore.app.db_router import atomic
from pulpcore.app.models import Artifact, Domain

from .test_multi_database_routing import SATELLITE_ALIAS, requires_multi_db

pytestmark = [requires_multi_db, pytest.mark.django_db(databases=["default", SATELLITE_ALIAS])]


@pytest.fixture
def satellite_domain():
    # Domain replication to the satellite is deferred via transaction.on_commit (see
    # domain_sync.on_domain_post_save), which never fires under pytest-django's test-wrapping
    # transaction unless explicitly flushed like this.
    with TestCase.captureOnCommitCallbacks(execute=True):
        domain = Domain.objects.create(
            name=f"oncommit-{uuid.uuid4().hex[:10]}",
            storage_class="pulpcore.app.models.storage.FileSystem",
            storage_settings={"location": "/tmp/oncommit-domain"},
            database_alias=SATELLITE_ALIAS,
        )
    yield domain
    domain.delete()


class TestOnCommitUsesTransactionAlias:
    def test_artifact_file_survives_satellite_rollback(self, satellite_domain):
        data = b"on-commit-alias-regression"
        digests = {
            algo: getattr(hashlib, algo)(data).hexdigest()
            for algo in ("sha224", "sha256", "sha384", "sha512")
        }
        with with_domain(satellite_domain):
            artifact = Artifact(
                file=ContentFile(data, name="regress.bin"), size=len(data), **digests
            )
            artifact.save()
        file_name = artifact.file.name
        storage = artifact.pulp_domain.get_storage()
        assert storage.exists(file_name)

        try:
            with pytest.raises(RuntimeError):
                with atomic(using=SATELLITE_ALIAS):
                    Artifact.objects.using(SATELLITE_ALIAS).get(pk=artifact.pk).delete()
                    raise RuntimeError("force rollback")

            # Rolled back: the row must still exist, AND its file must not have been deleted --
            # the bug was the on_commit file-delete firing against 'default' (no open transaction
            # there to wait on), independent of the satellite transaction's own fate.
            assert Artifact.objects.using(SATELLITE_ALIAS).filter(pk=artifact.pk).exists()
            assert storage.exists(file_name)
        finally:
            Artifact.objects.using(SATELLITE_ALIAS).filter(pk=artifact.pk).delete()
            if storage.exists(file_name):
                storage.delete(file_name)
