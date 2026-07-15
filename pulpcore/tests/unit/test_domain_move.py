"""
Integration tests for `move-domain`/`cleanup-moved-domain`/`domain-size` (phase2-move-domain,
phase2-cleanup), implementing Strategy A ("Read-Only Cutover") from
`architecture/domain-db-offloading-design.md`.

See `test_multi_database_routing.py`'s module docstring for why these require a real `data_1`
alias (set via `PULP_DATABASES__data_1__*` env vars) to run at all, rather than skipping.
"""

import hashlib

import pytest
from django.core.files.base import ContentFile
from django.core.management import call_command

from pulpcore.app.contexts import with_domain
from pulpcore.app.models import (
    Artifact,
    ContentArtifact,
    Domain,
    DomainMove,
)

from pulp_file.app.models import FileContent, FileRepository

from .test_multi_database_routing import SATELLITE_ALIAS, requires_multi_db

pytestmark = [requires_multi_db, pytest.mark.django_db(databases=["default", SATELLITE_ALIAS])]


@pytest.fixture
def hot_domain(tmp_path):
    domain = Domain.objects.create(
        name="move-test-domain",
        storage_class="pulpcore.app.models.storage.FileSystem",
        storage_settings={"location": str(tmp_path)},
    )
    with with_domain(domain):
        repo = FileRepository.objects.create(name="move-test-repo", pulp_domain=domain)
        data = b"move-domain integration test content"
        digests = {
            alg: hashlib.new(alg, data).hexdigest()
            for alg in ("sha224", "sha256", "sha384", "sha512")
        }
        artifact = Artifact.objects.create(
            file=ContentFile(data, name="x"), size=len(data), pulp_domain=domain, **digests
        )
        content = FileContent.objects.create(
            relative_path="a/b.txt", digest=digests["sha256"], pulp_domain=domain
        )
        ContentArtifact.objects.create(artifact=artifact, content=content, relative_path="a/b.txt")
        version = repo.new_version()
        with version:
            version.add_content(FileContent.objects.filter(pk=content.pk))
    yield domain
    domain.refresh_from_db()
    for alias in {domain.database_alias, "default"}:
        # Order matters: Repository first (cascades RepositoryVersion/RepositoryContent), then
        # Content (cascades ContentArtifact), then Artifact last -- ContentArtifact.artifact is
        # PROTECT, so deleting Artifact first (while a ContentArtifact still references it)
        # raises ProtectedError.
        FileRepository.objects.using(alias).filter(pulp_domain=domain).delete()
        FileContent.objects.using(alias).filter(pulp_domain=domain).delete()
        Artifact.objects.using(alias).filter(pulp_domain=domain).delete()
    domain.delete()


class TestMoveDomain:
    def test_move_domain_relocates_data_and_verifies_cleanly(self, hot_domain):
        call_command("move-domain", hot_domain.name, "--to", SATELLITE_ALIAS, "--noinput")

        hot_domain.refresh_from_db()
        assert hot_domain.database_alias == SATELLITE_ALIAS
        assert hot_domain.moving is False

        assert FileRepository.objects.using(SATELLITE_ALIAS).filter(pulp_domain=hot_domain).exists()
        assert Artifact.objects.using(SATELLITE_ALIAS).filter(pulp_domain=hot_domain).exists()
        # Strategy A / Step 7: the stale copy is deliberately left on the original alias until
        # 'cleanup-moved-domain' runs, so rollback is a one-line alias flip with no data loss.
        assert FileRepository.objects.using("default").filter(pulp_domain=hot_domain).exists()

        move = DomainMove.objects.using("default").get(domain=hot_domain, status="completed")
        assert move.from_alias == "default"
        assert move.to_alias == SATELLITE_ALIAS
        assert move.cutover_at is not None
        assert move.monitoring_until is not None

    def test_move_domain_refuses_default_domain(self):
        default_domain = Domain.objects.using("default").get(name="default")
        with pytest.raises(Exception, match="default"):
            call_command("move-domain", default_domain.name, "--to", SATELLITE_ALIAS, "--noinput")

    def test_move_domain_refuses_unconfigured_alias(self, hot_domain):
        with pytest.raises(Exception, match="not a configured"):
            call_command("move-domain", hot_domain.name, "--to", "not-a-real-alias", "--noinput")

    def test_move_domain_refuses_same_alias(self, hot_domain):
        with pytest.raises(Exception, match="already on alias"):
            call_command(
                "move-domain", hot_domain.name, "--to", hot_domain.database_alias, "--noinput"
            )


class TestCleanupMovedDomain:
    def test_cleanup_requires_force(self, hot_domain):
        call_command("move-domain", hot_domain.name, "--to", SATELLITE_ALIAS, "--noinput")
        with pytest.raises(Exception, match="--force"):
            call_command("cleanup-moved-domain", hot_domain.name)

    def test_cleanup_deletes_stale_source_copy(self, hot_domain):
        call_command("move-domain", hot_domain.name, "--to", SATELLITE_ALIAS, "--noinput")
        call_command("cleanup-moved-domain", hot_domain.name, "--force")

        hot_domain.refresh_from_db()
        assert not FileRepository.objects.using("default").filter(pulp_domain=hot_domain).exists()
        assert not Artifact.objects.using("default").filter(pulp_domain=hot_domain).exists()
        # The satellite copy (the domain's real, current data) must be untouched.
        assert FileRepository.objects.using(SATELLITE_ALIAS).filter(pulp_domain=hot_domain).exists()

        move = DomainMove.objects.using("default").get(domain=hot_domain, status="cleaned_up")
        assert move.cleaned_up_at is not None

    def test_cleanup_refuses_domain_still_on_default(self, hot_domain):
        with pytest.raises(Exception, match="nothing to clean up"):
            call_command("cleanup-moved-domain", hot_domain.name, "--force")


class TestDomainSize:
    def test_domain_size_reports_row_counts(self, hot_domain, capsys):
        call_command("domain-size", hot_domain.name)
        out = capsys.readouterr().out
        assert "file.FileRepository" in out
        assert "core.Artifact" in out
