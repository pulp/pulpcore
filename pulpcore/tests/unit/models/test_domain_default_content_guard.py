from uuid import uuid4

import pytest

from pulpcore.app.models import Distribution, Domain, DomainDefaultContentGuard, RBACContentGuard
from pulpcore.app.serializers import DomainSerializer

pytestmark = pytest.mark.django_db


@pytest.fixture
def domain():
    return Domain.objects.create(
        name=str(uuid4()), storage_class="pulpcore.app.models.storage.FileSystem"
    )


@pytest.fixture
def guard(domain):
    return RBACContentGuard.objects.create(name=str(uuid4()), pulp_domain=domain)


def test_set_replace_and_clear(domain, guard):
    assert domain.default_content_guard is None

    domain.set_default_content_guard(guard)
    assert domain.default_content_guard.pk == guard.pk
    assert Domain.objects.get(pk=domain.pk).default_content_guard.pk == guard.pk

    other = RBACContentGuard.objects.create(name=str(uuid4()), pulp_domain=domain)
    domain.set_default_content_guard(other)
    assert domain.default_content_guard.pk == other.pk
    assert DomainDefaultContentGuard.objects.filter(pulp_domain=domain).count() == 1

    domain.set_default_content_guard(None)
    assert domain.default_content_guard is None
    assert not DomainDefaultContentGuard.objects.filter(pulp_domain=domain).exists()


def test_deleting_guard_clears_default(domain, guard):
    domain.set_default_content_guard(guard)
    guard.delete()
    assert Domain.objects.get(pk=domain.pk).default_content_guard is None


def test_distribution_uses_default_guard(domain, guard):
    domain.set_default_content_guard(guard)
    explicit = RBACContentGuard.objects.create(name=str(uuid4()), pulp_domain=domain)

    inherited = Distribution.objects.create(name="a", base_path="a", pulp_domain=domain)
    assert inherited.content_guard_id == guard.pk
    chosen = Distribution.objects.create(
        name="b", base_path="b", pulp_domain=domain, content_guard=explicit
    )
    assert chosen.content_guard_id == explicit.pk


def test_distribution_without_default_guard(domain):
    distribution = Distribution.objects.create(name="a", base_path="a", pulp_domain=domain)
    assert distribution.content_guard_id is None


def test_serializer_update(domain, guard):
    serializer = DomainSerializer()
    serializer.update(domain, {"default_content_guard": guard})
    assert Domain.objects.get(pk=domain.pk).default_content_guard.pk == guard.pk

    # Updates that omit the field leave the default untouched.
    serializer.update(domain, {"description": "changed"})
    assert Domain.objects.get(pk=domain.pk).default_content_guard.pk == guard.pk

    serializer.update(domain, {"default_content_guard": None})
    assert Domain.objects.get(pk=domain.pk).default_content_guard is None
