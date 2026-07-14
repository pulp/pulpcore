"""
Integration tests for domain-aware database routing (phase1-integration-tests).

These tests exercise `PulpDomainRouter`, `migrate-all`, and graceful degradation
(phase1-graceful-degradation / KI-12) against **real** additional database aliases, per Django's
standard multi-database testing support (see "Testing multi-database applications" in the Django
testing docs): a second `settings.DATABASES` alias, `data_1`, and
`@pytest.mark.django_db(databases=[...])` to opt individual tests into it.

Unlike every other alias in this codebase, which is populated dynamically from
`PULP_DATABASES__<alias>__<KEY>` environment variables, `data_1` cannot be conjured up inside a
test: pytest-django creates/migrates the test database for every alias present in
`settings.DATABASES` once, at session start (`django_db_setup`), long before any individual test
runs -- there is no supported way to add a brand new alias from inside a test and have
pytest-django create a test database for it on the fly. So, for this entire module to actually
run against a real second database (rather than a no-op skip), the test environment must define
a `data_1` alias before pytest starts, e.g.:

    export PULP_DATABASES__data_1__ENGINE=django.db.backends.postgresql
    export PULP_DATABASES__data_1__NAME=pulp
    export PULP_DATABASES__data_1__USER=pulp
    export PULP_DATABASES__data_1__PASSWORD=pulp
    export PULP_DATABASES__data_1__HOST=<second-postgres-host>
    export PULP_DATABASES__data_1__PORT=<second-postgres-port>

When `data_1` isn't configured (the default for a single-database checkout/CI run), every test
below is skipped with a clear reason rather than silently doing nothing useful -- this mirrors
`PulpDomainRouter` itself only activating when `len(settings.DATABASES) > 1`, so there is no
meaningful "multi-db routing" behavior to test at all without it.
"""

from contextlib import contextmanager
from unittest import mock

import pytest
from django.conf import settings
from django.core.management import call_command
from django.db.utils import OperationalError

from pulpcore.app.contexts import with_domain
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
    SATELLITE_ALIAS not in settings.DATABASES,
    reason=(
        f"Multi-database routing tests require a '{SATELLITE_ALIAS}' alias in settings.DATABASES "
        f"(set PULP_DATABASES__{SATELLITE_ALIAS}__* env vars to a second real Postgres instance)."
    ),
)

pytestmark = [requires_multi_db, pytest.mark.django_db(databases=["default", SATELLITE_ALIAS])]


@contextmanager
def _satellite_domain(**extra_fields):
    """Create+clean up a Domain whose data-plane objects are routed to `data_1`."""
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
    """`migrate-all` (phase1-migrate-all) against a real second alias."""

    def test_migrate_all_migrates_every_alias(self):
        # pytest-django's `django_db_setup` already created+migrated the test database for
        # every configured alias (that's how `data_1` exists at all by the time this test runs),
        # so this call is expected to be a no-op -- the point is that it *completes cleanly* and
        # leaves a "complete" MigrationStatus row for every alias, exactly as it would against a
        # freshly provisioned satellite.
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
    """Data-plane routing by `Domain.database_alias` (phase1-router)."""

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
        """Saving an already-loaded satellite-domain instance routes correctly with no
        ContextVar set at all -- purely from `instance.pulp_domain` (the router's instance-hint
        path, `PulpDomainRouter._resolve_db`).

        Requires `select_related("pulp_domain")` on the fetch: post-KI-27, the router's
        instance-hint path only ever consults an *already-cached* `pulp_domain` relation object
        (never issues its own query for one -- that was the KI-27 N+1 bug), so a caller that
        wants correct instance-hint routing without a ContextVar must make sure the `Domain` is
        actually loaded, the same way `test_base.py::test_cast` does for `remote`.
        """
        with _satellite_domain(_suffix="instancehint") as domain:
            with with_domain(domain):
                repo = Repository.objects.create(name=f"{domain.name}-repo", pulp_domain=domain)
            try:
                # No `with_domain()`/ContextVar here: the previous `with` block has already
                # exited, so only the loaded instance's own `pulp_domain` FK can inform routing.
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
        """Task (control-plane) must stay on `default` even while a satellite domain is the
        active ContextVar -- KI-11/Locked Decisions: task coordination never moves off the
        control DB, regardless of which alias the *data* it operates on lives on."""
        with _satellite_domain(_suffix="controlplane") as domain:
            with with_domain(domain):
                task = Task.objects.create(name="test-task", state=TASK_STATES.WAITING)
            try:
                assert Task.objects.using("default").filter(pk=task.pk).exists()
                assert not Task.objects.using(SATELLITE_ALIAS).filter(pk=task.pk).exists()
            finally:
                Task.objects.using("default").filter(pk=task.pk).delete()


class TestRouterInstanceHintSafety:
    """KI-27 regressions against `PulpDomainRouter._resolve_db`'s instance-hint path.

    Both bugs share a root cause: the old code used `hasattr()`/`getattr()` to read
    `pulp_domain_id`/`pulp_domain` off the hinted instance, which can trigger Django's
    `DeferredAttribute.__get__` fallback (a fresh query, or -- worse -- a `refresh_from_db()`
    call that re-enters the router with the very same not-yet-constructed instance and recurses
    until `RecursionError`). The fix inspects `instance.__dict__` /
    `instance._state.fields_cache` directly instead, which can never trigger either fallback.
    """

    def test_remote_artifact_construction_does_not_recurse(self):
        """Reproduces the crash directly: `RemoteArtifact` declares `content_artifact` and
        `remote` *before* `pulp_domain` in field order (see `models/content.py`), so
        constructing one with an unsaved `ContentArtifact` -- exactly how
        `content/handler.py`'s pull-through path builds it, e.g. around line 909:
        `RemoteArtifact(remote=remote, url=url, content_artifact=ca)` -- used to recurse
        infinitely the moment `len(settings.DATABASES) > 1` activated the router: assigning
        `content_artifact` makes Django's `ForwardManyToOneDescriptor.__set__` ask the router to
        resolve a DB for the (unsaved) `ContentArtifact` value, hinting the half-built
        `RemoteArtifact` itself back into `_resolve_db`, which then tried to read
        `pulp_domain_id` off of it before that field had been assigned at all.
        """
        with _satellite_domain(_suffix="norecursion") as domain:
            with with_domain(domain):
                remote = Remote.objects.create(name="ki27-remote", url="https://example.com")
                # Unsaved, with no `pulp_domain` set yet -- matches how handler.py builds it.
                ca = ContentArtifact(relative_path="ki27/path")
                try:
                    ra = RemoteArtifact(remote=remote, url=f"{remote.url}/x", content_artifact=ca)
                except RecursionError:
                    pytest.fail(
                        "PulpDomainRouter._resolve_db recursed while constructing a "
                        "RemoteArtifact with a preceding unsaved FK -- KI-27 regression"
                    )
            try:
                # Not just "didn't crash" -- resolved the *correct* domain via the ContextVar
                # fallback once the instance-hint path safely declined to use a not-yet-set
                # `pulp_domain_id`.
                assert ra.pulp_domain_id == domain.pk
            finally:
                Remote.objects.using(SATELLITE_ALIAS).filter(pk=remote.pk).delete()

    def test_relation_access_does_not_issue_extra_domain_query(self, django_assert_num_queries):
        """KI-27's N+1 half: reading a data-plane relation (`repository.remote`) off an
        already-loaded instance that has `pulp_domain_id` set but no cached `pulp_domain`
        relation object must resolve through the router in exactly the number of queries the
        relation access itself needs -- zero extra queries to fetch `Domain` just to ask the
        router which alias to use. Mirrors `test_base.py::test_cast`, scoped explicitly to a
        real multi-DB configuration (`len(settings.DATABASES) > 1`, the condition that actually
        activates `PulpDomainRouter` -- see the module docstring in `db_router.py`).
        """
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
    """503 on unreachable/moving satellite (phase1-graceful-degradation / KI-12)."""

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
            # Real connection check against the actual (reachable, in this test run) satellite --
            # no mocking -- to prove the happy path doesn't false-positive.
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
        """A worker must not attempt to run a task whose domain is mid-move -- it should stay
        `waiting`, not be picked up (and definitely not fail)."""
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
