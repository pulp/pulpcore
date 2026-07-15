"""
Integration tests for the KI-11 cross-plane reconciliation sweep (phase3-monitoring).

See `test_multi_database_routing.py`'s module docstring for why these require a real `data_1`
alias (set via `PULP_DATABASES__data_1__*` env vars) to run at all, rather than skipping.
"""

from datetime import timedelta

import pytest
from django.core.management import call_command
from django.utils import timezone

from pulpcore.app.contexts import with_domain, with_task_context
from pulpcore.app.models import CreatedResource, Domain, Task
from pulpcore.app.tasks.reconciliation import reconcile_cross_plane_references

from pulp_file.app.models import FileRepository

from .test_multi_database_routing import SATELLITE_ALIAS, requires_multi_db

pytestmark = [requires_multi_db, pytest.mark.django_db(databases=["default", SATELLITE_ALIAS])]


@pytest.fixture
def satellite_domain():
    domain = Domain.objects.create(
        name="reconcile-test-domain",
        storage_class="pulpcore.app.models.storage.FileSystem",
        storage_settings={"location": "/tmp/reconcile-test-domain"},
        database_alias=SATELLITE_ALIAS,
    )
    yield domain
    domain.delete()


@pytest.fixture
def task():
    t = Task.objects.create(name="reconcile-test-task")
    yield t
    t.delete()


def _backdate(created_resource, minutes):
    CreatedResource.objects.using("default").filter(pk=created_resource.pk).update(
        pulp_last_updated=timezone.now() - timedelta(minutes=minutes)
    )
    created_resource.refresh_from_db()


class TestReconcileCrossPlaneReferences:
    def test_healthy_cross_plane_reference_is_not_flagged(self, satellite_domain, task):
        with with_task_context(task), with_domain(satellite_domain):
            repo = FileRepository.objects.create(
                name="reconcile-healthy-repo", pulp_domain=satellite_domain
            )
            cr = CreatedResource.objects.create(content_object=repo)
        _backdate(cr, minutes=120)

        report = reconcile_cross_plane_references(grace_period_minutes=60)

        assert report["checked"] >= 1
        assert report["orphaned"] == 0
        assert str(cr.pk) not in {o["pk"] for o in report["orphans"]}

    def test_orphaned_reference_is_detected_but_not_purged_by_default(self, satellite_domain, task):
        with with_task_context(task), with_domain(satellite_domain):
            repo = FileRepository.objects.create(
                name="reconcile-orphan-repo", pulp_domain=satellite_domain
            )
            cr = CreatedResource.objects.create(content_object=repo)
        repo.delete(using=SATELLITE_ALIAS)
        _backdate(cr, minutes=120)

        report = reconcile_cross_plane_references(grace_period_minutes=60, purge_after_days=0)

        assert report["orphaned"] == 1
        assert report["purged"] == 0
        assert CreatedResource.objects.using("default").filter(pk=cr.pk).exists()
        orphan = report["orphans"][0]
        assert orphan["pk"] == str(cr.pk)
        assert orphan["alias"] == SATELLITE_ALIAS

    def test_orphaned_reference_within_grace_period_is_skipped(self, satellite_domain, task):
        with with_task_context(task), with_domain(satellite_domain):
            repo = FileRepository.objects.create(
                name="reconcile-fresh-orphan-repo", pulp_domain=satellite_domain
            )
            cr = CreatedResource.objects.create(content_object=repo)
        repo.delete(using=SATELLITE_ALIAS)
        # No backdating: this row is "fresh" and should be skipped regardless of the grace period.

        report = reconcile_cross_plane_references(grace_period_minutes=60)

        assert str(cr.pk) not in {o["pk"] for o in report["orphans"]}

    def test_purge_after_days_deletes_old_confirmed_orphans(self, satellite_domain, task):
        with with_task_context(task), with_domain(satellite_domain):
            repo = FileRepository.objects.create(
                name="reconcile-purge-repo", pulp_domain=satellite_domain
            )
            cr = CreatedResource.objects.create(content_object=repo)
        repo.delete(using=SATELLITE_ALIAS)
        _backdate(cr, minutes=60 * 24 * 10)

        report = reconcile_cross_plane_references(
            grace_period_minutes=60, purge_after_days=7, dry_run=False
        )

        assert report["orphaned"] == 1
        assert report["purged"] == 1
        assert not CreatedResource.objects.using("default").filter(pk=cr.pk).exists()

    def test_dry_run_never_purges(self, satellite_domain, task):
        with with_task_context(task), with_domain(satellite_domain):
            repo = FileRepository.objects.create(
                name="reconcile-dry-run-repo", pulp_domain=satellite_domain
            )
            cr = CreatedResource.objects.create(content_object=repo)
        repo.delete(using=SATELLITE_ALIAS)
        _backdate(cr, minutes=60 * 24 * 10)

        report = reconcile_cross_plane_references(
            grace_period_minutes=60, purge_after_days=7, dry_run=True
        )

        assert report["orphaned"] == 1
        assert report["purged"] == 0
        assert CreatedResource.objects.using("default").filter(pk=cr.pk).exists()

    def test_management_command_reports_orphans(self, satellite_domain, task, capsys):
        with with_task_context(task), with_domain(satellite_domain):
            repo = FileRepository.objects.create(
                name="reconcile-cmd-repo", pulp_domain=satellite_domain
            )
            cr = CreatedResource.objects.create(content_object=repo)
        repo.delete(using=SATELLITE_ALIAS)
        _backdate(cr, minutes=120)

        call_command("reconcile-cross-plane-references", "--grace-period-minutes", "60")

        out = capsys.readouterr().out
        assert "1 orphan(s)" in out or "found 1 orphan" in out.lower()
