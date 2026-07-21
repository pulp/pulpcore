from unittest.mock import MagicMock, patch

from django.test import TestCase

from pulpcore.middleware import DomainMiddleware
from pulpcore.plugin.find_url import find_api_root


class TestLivezNoDatabaseAccess(TestCase):
    """Test that GET /livez/ makes zero database queries."""

    def test_livez_makes_no_database_queries(self):
        _, api_v3_path = find_api_root(set_domain=False, rewrite_header=False)
        with self.assertNumQueries(0):
            response = self.client.get(f"{api_v3_path}livez/")
        self.assertEqual(response.status_code, 200)


class TestDomainMiddlewareSkip(TestCase):
    """Test that DomainMiddleware skips DB lookup for views with skip_domain_middleware=True."""

    def setUp(self):
        self.middleware = DomainMiddleware(get_response=MagicMock())
        self.request = MagicMock()

    @patch("pulpcore.middleware.Domain.objects")
    @patch("pulpcore.middleware.set_domain")
    def test_does_db_lookup_when_flag_not_set(self, mock_set_domain, mock_domain_objects):
        view_class = type("NormalView", (), {})
        view_func = MagicMock(view_class=view_class)
        view_kwargs = {"pulp_domain": "default"}
        # database_alias/moving must be set explicitly: an unconfigured MagicMock() would make
        # `_degraded_response`'s `alias != "default"` check true, sending it into a real
        # `connections[alias]` lookup with a MagicMock alias, which isn't what this test is
        # about (it only cares whether the DB lookup/skip-flag behavior is exercised).
        mock_domain_objects.get.return_value = MagicMock(database_alias="default", moving=False)

        self.middleware.process_view(self.request, view_func, [], view_kwargs)

        mock_domain_objects.get.assert_called_once_with(name="default")
