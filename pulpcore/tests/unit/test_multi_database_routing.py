from contextlib import contextmanager
from unittest import mock

import pytest
from django.conf import settings
from django.core.management import call_command
from django.db.utils import OperationalError

from pulpcore.app.contexts import with_domain
from pulpcore.app.db_router import is_multi_db_routing_active
from pulpcore.app.models import (
    ContentArtifact,
    Domain,
    MigrationStatus,
    Remote,
    RemoteArtifact,
    Repository,
    Task,
)
from pulpcore.constants import TASK_STATES

SATELLITE_ALIAS = "data_1"

requires_multi_db = pytest.mark.skipif(
    SATELLITE_ALIAS not in settings.DATABASES or not is_multi_db_routing_active(),
    reason=(
        f"Multi-database routing tests require a '{SATELLITE_ALIAS}' alias in settings.DATABASES "
        f"(set PULP_DATABASES__{SATELLITE_ALIAS}__* env vars to a second real Postgres instance) "
        "and PulpDomainRouter registered in DATABASE_ROUTERS."
    ),
)

pytestmark = [requires_multi_db, pytest.mark.django_db(databases=["default", SATELLITE_ALIAS])]


@contextmanager
def _satellite_domain(**extra_fields):
    domain = Domain.objects.create(
        name=f"test-satellite-domain-{extra_fields.get('_suffix', '')}".rstrip("-"),
        storage_class="pulpcore.app.models.storage.FileSystem",
        database_alias=SATELLITE_ALIAS,
        **{k: v for k, v in extra_fields.items() if k != "_suffix"},
    )
    try:
        yield domain
    finally:
        domain.delete()


class TestMigrateAll:
    def test_migrate_all_migrates_every_alias(self):
        call_command("migrate-all")

        statuses = {m.database_alias: m.status for m in MigrationStatus.objects.all()}
        for alias in settings.DATABASES:
            assert statuses.get(alias) == "complete", (
                f"Expected MigrationStatus for alias '{alias}' to be 'complete', got "
                f"{statuses.get(alias)!r}"
            )

    def test_migrate_all_reconciles_domain_table_to_satellite(self):
        call_command("migrate-all")

        default_domain = Domain.objects.using("default").get(name="default")
        assert Domain.objects.using(SATELLITE_ALIAS).filter(pk=default_domain.pk).exists(), (
            "The 'default' Domain row should have been replicated onto the satellite alias by "
            "migrate-all's Domain-sync step."
        )


class TestPulpDomainRouter:
    def test_data_plane_object_routes_to_satellite_alias(self):
        with _satellite_domain(_suffix="routing") as domain:
            with with_domain(domain):
                repo = Repository.objects.create(name=f"{domain.name}-repo", pulp_domain=domain)
            try:
                assert Repository.objects.using(SATELLITE_ALIAS).filter(pk=repo.pk).exists(), (
                    "Repository created under a satellite-domain context should exist on the "
                    "satellite alias."
                )
                assert not Repository.objects.using("default").filter(pk=repo.pk).exists(), (
                    "Repository created under a satellite-domain context must NOT exist on "
                    "'default' -- routing to the wrong alias would silently duplicate/leak data."
                )
            finally:
                Repository.objects.using(SATELLITE_ALIAS).filter(pk=repo.pk).delete()

    def test_instance_hint_routes_without_contextvar(self):
        with _satellite_domain(_suffix="instancehint") as domain:
            with with_domain(domain):
                repo = Repository.objects.create(name=f"{domain.name}-repo", pulp_domain=domain)
            try:
                repo_fresh = (
                    Repository.objects.using(SATELLITE_ALIAS)
                    .select_related("pulp_domain")
                    .get(pk=repo.pk)
                )
                repo_fresh.description = "updated via instance hint, no ContextVar"
                repo_fresh.save()
                assert (
                    Repository.objects.using(SATELLITE_ALIAS).get(pk=repo.pk).description
                    == "updated via instance hint, no ContextVar"
                )
            finally:
                Repository.objects.using(SATELLITE_ALIAS).filter(pk=repo.pk).delete()

    def test_control_plane_model_always_routes_to_default(self):
        with _satellite_domain(_suffix="controlplane") as domain:
            with with_domain(domain):
                task = Task.objects.create(name="test-task", state=TASK_STATES.WAITING)
            try:
                assert Task.objects.using("default").filter(pk=task.pk).exists()
                assert not Task.objects.using(SATELLITE_ALIAS).filter(pk=task.pk).exists()
            finally:
                Task.objects.using("default").filter(pk=task.pk).delete()


class TestRouterInstanceHintSafety:
    def test_remote_artifact_construction_does_not_recurse(self):
        with _satellite_domain(_suffix="norecursion") as domain:
            with with_domain(domain):
                remote = Remote.objects.create(name="ki27-remote", url="https://example.com")
                ca = ContentArtifact(relative_path="ki27/path")
                try:
                    ra = RemoteArtifact(remote=remote, url=f"{remote.url}/x", content_artifact=ca)
                except RecursionError:
                    pytest.fail(
                        "PulpDomainRouter._resolve_db recursed while constructing a "
                        "RemoteArtifact with a preceding unsaved FK"
                    )
            try:
                assert ra.pulp_domain_id == domain.pk
            finally:
                Remote.objects.using(SATELLITE_ALIAS).filter(pk=remote.pk).delete()

    def test_relation_access_does_not_issue_extra_domain_query(self, django_assert_num_queries):
        from pulp_file.app.models import FileRemote, FileRepository

        remote = FileRemote.objects.create(name="ki27-cast-remote")
        repository = FileRepository.objects.create(name="ki27-cast-repo", remote=remote)
        try:
            with django_assert_num_queries(1):
                fetched = Repository.objects.get(pk=repository.pk)
            with django_assert_num_queries(1):
                fetched = fetched.cast()
            with django_assert_num_queries(1):
                assert fetched.remote.pk == remote.pk
        finally:
            repository.delete()
            remote.delete()


class TestGracefulDegradation:
    def test_503_when_satellite_unreachable(self):
        from pulpcore.middleware import DomainMiddleware

        with _satellite_domain(_suffix="unreachable") as domain:
            request = mock.Mock(method="GET")
            with mock.patch("pulpcore.middleware.connections") as mock_connections:
                mock_connections.__getitem__.return_value.ensure_connection.side_effect = (
                    OperationalError("could not connect")
                )
                response = DomainMiddleware._degraded_response(request, domain)

            assert response is not None
            assert response.status_code == 503
            assert domain.name in response.content.decode()

    def test_no_503_when_satellite_reachable(self):
        with _satellite_domain(_suffix="reachable") as domain:
            from pulpcore.middleware import DomainMiddleware

            request = mock.Mock(method="GET")
            response = DomainMiddleware._degraded_response(request, domain)
            assert response is None

    def test_503_rejects_writes_to_moving_domain(self):
        with _satellite_domain(_suffix="moving", moving=True) as domain:
            from pulpcore.middleware import DomainMiddleware

            write_request = mock.Mock(method="POST")
            response = DomainMiddleware._degraded_response(write_request, domain)
            assert response is not None
            assert response.status_code == 503

            read_request = mock.Mock(method="GET")
            assert DomainMiddleware._degraded_response(read_request, domain) is None

    def test_task_dispatch_skips_moving_domain(self):
        from pulpcore.tasking.worker import PulpcoreWorker

        with _satellite_domain(_suffix="taskmoving", moving=True) as domain:
            with with_domain(domain):
                task = Task.objects.create(name="test-task", state=TASK_STATES.WAITING)
            try:
                worker = mock.Mock(spec=PulpcoreWorker)
                assert PulpcoreWorker.is_domain_available(worker, task) is False
            finally:
                Task.objects.using("default").filter(pk=task.pk).delete()

    def test_task_dispatch_skips_unreachable_satellite(self):
        from pulpcore.tasking.worker import PulpcoreWorker

        with _satellite_domain(_suffix="taskunreachable") as domain:
            with with_domain(domain):
                task = Task.objects.create(name="test-task", state=TASK_STATES.WAITING)
            try:
                worker = mock.Mock(spec=PulpcoreWorker)
                with mock.patch("pulpcore.tasking.worker.connections") as mock_connections:
                    mock_connections.__getitem__.return_value.ensure_connection.side_effect = (
                        OperationalError("could not connect")
                    )
                    assert PulpcoreWorker.is_domain_available(worker, task) is False
            finally:
                Task.objects.using("default").filter(pk=task.pk).delete()

    def test_task_dispatch_allows_healthy_domain(self):
        from pulpcore.tasking.worker import PulpcoreWorker

        with _satellite_domain(_suffix="taskhealthy") as domain:
            with with_domain(domain):
                task = Task.objects.create(name="test-task", state=TASK_STATES.WAITING)
            try:
                worker = mock.Mock(spec=PulpcoreWorker)
                assert PulpcoreWorker.is_domain_available(worker, task) is True
            finally:
                Task.objects.using("default").filter(pk=task.pk).delete()
