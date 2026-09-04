from uuid import uuid4

import pytest

from pulpcore.app.contexts import with_task_context
from pulpcore.app.models import CreatedResource, RepositoryVersion, Task
from pulpcore.app.models.generic import _resolve_domain_id

from pulp_file.app.models import FileRepository


@pytest.fixture
def task():
    t = Task.objects.create(name="test-generic-relation-task")
    yield t
    t.delete()


@pytest.mark.django_db
def test_content_object_returns_none_for_deleted_domain_scoped_target(task):
    with with_task_context(task):
        repository = FileRepository.objects.create(name=str(uuid4()))
        created_resource = CreatedResource.objects.create(content_object=repository)
    assert created_resource.content_object_domain_id is not None

    repository.delete()

    created_resource = CreatedResource.objects.get(pk=created_resource.pk)
    assert created_resource.content_object is None


@pytest.mark.django_db
def test_content_object_resolves_existing_domain_scoped_target(task):
    with with_task_context(task):
        repository = FileRepository.objects.create(name=str(uuid4()))
        created_resource = CreatedResource.objects.create(content_object=repository)

    created_resource = CreatedResource.objects.get(pk=created_resource.pk)
    resolved = created_resource.content_object
    assert resolved is not None
    assert resolved.pk == repository.pk


@pytest.mark.django_db
def test_resolve_domain_id_walks_transitive_fk(task):
    with with_task_context(task):
        repository = FileRepository.objects.create(name=str(uuid4()))
    version = RepositoryVersion.objects.create(repository=repository, number=1)

    assert getattr(version, "pulp_domain_id", None) is None
    assert _resolve_domain_id(version) == repository.pulp_domain_id


@pytest.mark.django_db
def test_content_object_domain_id_set_for_repository_version(task):
    with with_task_context(task):
        repository = FileRepository.objects.create(name=str(uuid4()))
        version = RepositoryVersion.objects.create(repository=repository, number=1)
        created_resource = CreatedResource.objects.create(content_object=version)
    assert created_resource.content_object_domain_id == repository.pulp_domain_id

    created_resource = CreatedResource.objects.get(pk=created_resource.pk)
    resolved = created_resource.content_object
    assert resolved is not None
    assert resolved.pk == version.pk
