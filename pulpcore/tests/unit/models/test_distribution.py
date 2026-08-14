import pytest
from django.db import connection
from django.db.utils import IntegrityError

from pulpcore.app.models import Distribution

# "SET CONSTRAINTS ALL IMMEDIATE" is automatically called by the fixtures teardown.
# We only need to do it manually when we need the exception during the test.


@pytest.mark.django_db
class TestDistributionBasePathConstraint:
    def test_must_be_unique(self):
        Distribution(name="0", base_path="a").save()
        with pytest.raises(IntegrityError, match="unique constraint"):
            Distribution(name="1", base_path="a").save()

    def test_can_share_a_prefix_with_another_base_path(self):
        Distribution(name="0", base_path="a/a").save()
        Distribution(name="1", base_path="a/b").save()

    def test_cannot_be_the_prefix_of_another_base_path(self):
        Distribution(name="0", base_path="a/a").save()
        Distribution(name="1", base_path="a").save()
        with pytest.raises(IntegrityError, match="prefix"):
            with connection.cursor() as cursor:
                cursor.execute("SET CONSTRAINTS ALL IMMEDIATE")

    def test_cannot_contain_another_base_path_as_prefix(self):
        Distribution(name="0", base_path="a").save()
        Distribution(name="1", base_path="a/a").save()
        with pytest.raises(IntegrityError, match="prefix"):
            with connection.cursor() as cursor:
                cursor.execute("SET CONSTRAINTS ALL IMMEDIATE")

    def test_prefixes_are_checke_at_slash_boundaries(self):
        Distribution(name="0", base_path="abc").save()
        Distribution(name="1", base_path="ab").save()
        Distribution(name="2", base_path="abcd").save()
        Distribution(name="3", base_path="abcde/a").save()
