from contextlib import contextmanager

import pytest
from django.conf import settings

from pulpcore.app.contexts import with_domain
from pulpcore.app.db_router import is_multi_db_routing_active
from pulpcore.app.models import ContentArtifact, Domain, Remote, RemoteArtifact, Repository, Task
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
