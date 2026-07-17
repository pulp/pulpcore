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
    """A CreatedResource whose target was deleted must resolve to None, not raise.

    Every data-plane model has ``pulp_domain_id`` set, so ``content_object_domain`` is always
    populated for a resource like ``FileRepository`` -- even in a single-database deployment
    with no satellites configured. Regression test for the KI-18 cross-plane ``content_object``
    resolution (`pulpcore.app.models.generic.DomainResolvedGenericRelation`): deleting the
    target used to raise ``DoesNotExist`` out of the property instead of returning ``None``
    like Django's own ``GenericForeignKey`` (and every caller, e.g. ``RelatedResourceField``)
    expects.
    """
    with with_task_context(task):
        repository = FileRepository.objects.create(name=str(uuid4()))
        created_resource = CreatedResource.objects.create(content_object=repository)
    assert created_resource.content_object_domain_id is not None

    repository.delete()

    # Force a fresh lookup instead of the in-memory cache populated by the setter above.
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
    """Regression test for the 2026-07-17 KI-18 correction.

    ``RepositoryVersion`` has no ``pulp_domain`` field of its own -- only its parent
    ``Repository`` does -- so a bare ``getattr(value, "pulp_domain_id", None)`` always returns
    ``None`` for it. ``_resolve_domain_id()`` must walk the ``.repository`` FK to find it.
    """
    with with_task_context(task):
        repository = FileRepository.objects.create(name=str(uuid4()))
    version = RepositoryVersion.objects.create(repository=repository, number=1)

    assert getattr(version, "pulp_domain_id", None) is None
    assert _resolve_domain_id(version) == repository.pulp_domain_id


@pytest.mark.django_db
def test_content_object_domain_id_set_for_repository_version(task):
    """``RepositoryVersion`` is the single most common ``CreatedResource`` target in pulpcore
    (every sync/publish creates one) -- this must not silently regress to ``domain_id=None``.
    """
    with with_task_context(task):
        repository = FileRepository.objects.create(name=str(uuid4()))
    version = RepositoryVersion.objects.create(repository=repository, number=1)

    created_resource = CreatedResource.objects.create(content_object=version)
    assert created_resource.content_object_domain_id == repository.pulp_domain_id

    created_resource = CreatedResource.objects.get(pk=created_resource.pk)
    resolved = created_resource.content_object
    assert resolved is not None
    assert resolved.pk == version.pk
