"""
Regression test: CreatedResource.save() unconditionally skipped persisting whenever multi-db
routing was active, to avoid content_object (a plain GenericForeignKey) pointing at a data-plane
object on a different database than CreatedResource's own (control-plane, always 'default') row
-- a real cross-database relationship that can't be represented. But that blanket early return
also disabled tracking for a target that happens to live in 'default' itself (e.g. the default
domain, or any domain not mapped to a satellite), where there's no cross-database relationship
at all -- and task-cancellation cleanup depends on this tracking existing.
"""

import pytest
from django.test import TestCase

from pulpcore.app.contexts import with_domain
from pulpcore.app.models import Domain, Repository, Task
from pulpcore.app.models.task import CreatedResource
from pulpcore.constants import TASK_STATES

from .test_multi_database_routing import SATELLITE_ALIAS, requires_multi_db

pytestmark = [requires_multi_db, pytest.mark.django_db(databases=["default", SATELLITE_ALIAS])]


@pytest.fixture
def satellite_domain():
    # Domain replication to the satellite is deferred via transaction.on_commit (see
    # domain_sync.on_domain_post_save), which never fires under pytest-django's test-wrapping
    # transaction unless explicitly flushed like this.
    with TestCase.captureOnCommitCallbacks(execute=True):
        domain = Domain.objects.create(
            name="created-resource-tracking-domain",
            storage_class="pulpcore.app.models.storage.FileSystem",
            storage_settings={"location": "/tmp/created-resource-tracking-domain"},
            database_alias=SATELLITE_ALIAS,
        )
    yield domain
    domain.delete()


class TestCreatedResourceTrackingPreservedForDefault:
    def test_tracking_persists_for_default_target(self):
        task = Task.objects.create(name="regress-cr-task", state=TASK_STATES.WAITING)
        other_task = Task.objects.create(name="regress-cr-task-2", state=TASK_STATES.WAITING)
        try:
            # content_object (the tracked target) lives in 'default' -- Task is control-plane --
            # so there's no cross-database relationship here at all, and tracking should work
            # exactly as it would with multi-db routing inactive.
            resource = CreatedResource(content_object=task, task=other_task)
            resource.save()

            assert CreatedResource.objects.using("default").filter(pk=resource.pk).exists()
        finally:
            Task.objects.using("default").filter(pk__in=[task.pk, other_task.pk]).delete()

    def test_tracking_still_skipped_for_satellite_target(self, satellite_domain):
        with with_domain(satellite_domain):
            repo = Repository.objects.create(name="cr-tracking-repo", pulp_domain=satellite_domain)
        task = Task.objects.create(name="regress-cr-task-sat", state=TASK_STATES.WAITING)
        try:
            resource = CreatedResource(content_object=repo, task=task)
            resource.save()
            # Explicit, documented limitation: a satellite target still isn't tracked, since
            # CreatedResource (control-plane) can't hold a real cross-database relationship to it.
            assert not CreatedResource.objects.using("default").filter(pk=resource.pk).exists()
        finally:
            Task.objects.using("default").filter(pk=task.pk).delete()
            Repository.objects.using(SATELLITE_ALIAS).filter(pk=repo.pk).delete()
