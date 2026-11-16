from uuid import uuid4

import pytest
from django.contrib.auth import get_user_model
from django.test import TestCase

from pulpcore.app.models import Domain, Group, Task
from pulpcore.app.role_util import assign_role, get_objects_for_user
from pulpcore.constants import TASK_STATES

from .test_multi_database_routing import SATELLITE_ALIAS, requires_multi_db

pytestmark = [requires_multi_db, pytest.mark.django_db(databases=["default", SATELLITE_ALIAS])]


@pytest.fixture
def satellite_domain():
    with TestCase.captureOnCommitCallbacks(execute=True):
        domain = Domain.objects.create(
            name=str(uuid4()),
            storage_class="pulpcore.app.models.storage.FileSystem",
            database_alias=SATELLITE_ALIAS,
        )
    yield domain


@pytest.mark.parametrize("filtered", [False, True])
@pytest.mark.parametrize("group_grant", [False, True])
def test_satellite_domain_grant_scopes_tasks(satellite_domain, filtered, group_grant):
    """Domain grants live in the domain's database, while Tasks always live in 'default'."""
    user = get_user_model().objects.create(username=str(uuid4()))
    entity = user
    if group_grant:
        entity = Group.objects.create(name=str(uuid4()))
        entity.user_set.add(user)
    task = Task.objects.create(
        name=str(uuid4()), state=TASK_STATES.COMPLETED, pulp_domain=satellite_domain
    )
    other = Task.objects.create(name=str(uuid4()), state=TASK_STATES.COMPLETED)

    qs = Task.objects.filter(pk__in=[task.pk, other.pk])
    if filtered:
        qs = qs.filter(pulp_domain=satellite_domain)
        setattr(qs, "filtered_domain", satellite_domain)
    assert not get_objects_for_user(user, "core.view_task", qs).exists()

    grant = assign_role("core.task_viewer", entity, domain=satellite_domain)
    assert grant._state.db == SATELLITE_ALIAS
    assert list(get_objects_for_user(user, "core.view_task", qs)) == [task]
