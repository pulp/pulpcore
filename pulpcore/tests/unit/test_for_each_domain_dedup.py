import pytest
from django.conf import settings
from django.core.management import call_command
from django.db import connections

from pulpcore.app.contexts import with_domain
from pulpcore.app.models import Domain, Remote
from pulpcore.app.util import for_each_alias

pytestmark = pytest.mark.django_db


class TestForEachAlias:
    def test_iterates_every_configured_alias(self):
        seen = []
        for_each_alias(seen.append)
        assert sorted(seen) == sorted(settings.DATABASES)


class TestDatarepair2327DomainDedup:
    """Regression test for review comment on PR #7862: for_each_domain callers that don't
    filter by pulp_domain reprocess the same alias-wide data once per domain sharing that
    alias. datarepair-2327 is the simplest repro since it just counts affected Remotes."""

    def test_remote_on_shared_alias_counted_once_per_domain_sharing_it(self, capsys):
        extra_domain = Domain.objects.create(
            name="test-2327-dedup-domain",
            storage_class="pulpcore.app.models.storage.FileSystem",
            database_alias="default",
        )
        default_domain = Domain.objects.get(name="default")
        try:
            with with_domain(default_domain):
                remote = Remote.objects.create(
                    name="test-2327-dedup-remote",
                    url="https://example.com",
                    username="placeholder",
                )

            # Simulate the historical corruption this command repairs: the raw column holds
            # plaintext instead of a Fernet token, bypassing the EncryptedTextField descriptor.
            with connections["default"].cursor() as cursor:
                cursor.execute(
                    "UPDATE core_remote SET username = %s WHERE pulp_id = %s",
                    ["plaintext-leak", str(remote.pk)],
                )

            call_command("datarepair-2327", "--dry-run")
            output = capsys.readouterr().out

            assert "Remotes with un-encrypted fields: 1" in output, (
                f"Expected exactly one affected remote regardless of how many domains share "
                f"the 'default' alias, got: {output!r}"
            )
        finally:
            # Raw delete: the ORM path would decrypt the now-corrupted username column again.
            with connections["default"].cursor() as cursor:
                cursor.execute("DELETE FROM core_remote WHERE pulp_id = %s", [str(remote.pk)])
            extra_domain.delete()
