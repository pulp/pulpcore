"""Tests that look at generic list endpoints."""
import tempfile
import unittest

from pulp_smash import config, utils
from pulp_smash.pulp3.bindings import delete_orphans, monitor_task
from pulp_smash.pulp3.utils import gen_repo

from pulpcore.tests.functional.api.using_plugin.constants import X509_CA_CERT_FILE_PATH
from pulpcore.tests.functional.utils import set_up_module as setUpModule  # noqa:F401

from pulpcore.client.pulpcore import (
    ApiClient as CoreApiClient,
    ContentApi,
    ContentguardsApi,
    RepositoriesApi,
)
from pulpcore.client.pulp_file import (
    ApiClient as FileApiClient,
    ContentFilesApi,
    RepositoriesFileApi,
)

from pulpcore.client.pulp_certguard import (
    ApiClient as CertGuardApiClient,
    ContentguardsX509Api,
)


class GenericListTestCase(unittest.TestCase):
    """Test generic list endpoints."""

    @classmethod
    def setUpClass(cls):
        """Create class-wide variables."""
        cls.cfg = config.get_config()
        cls.file_repositories_api = RepositoriesFileApi(
            FileApiClient(cls.cfg.get_bindings_config())
        )
        cls.repo = cls.file_repositories_api.create(gen_repo())

        cls.file_content_api = ContentFilesApi(FileApiClient(cls.cfg.get_bindings_config()))
        with tempfile.NamedTemporaryFile() as tmp_file:
            tmp_file.write(b"not empty")
            tmp_file.flush()
            monitor_task(
                cls.file_content_api.create(relative_path=utils.uuid4(), file=tmp_file.name).task
            )

        cls.cert_guards_api = ContentguardsX509Api(
            CertGuardApiClient(cls.cfg.get_bindings_config())
        )
        with open(X509_CA_CERT_FILE_PATH, "r") as x509_ca_cert_data_file:
            x509_ca_cert_data = x509_ca_cert_data_file.read()

        cls.content_guard = cls.cert_guards_api.create(
            {"name": utils.uuid4(), "ca_certificate": x509_ca_cert_data}
        )

    @classmethod
    def tearDownClass(cls):
        """Cleanup class-wide variables."""
        monitor_task(cls.file_repositories_api.delete(cls.repo.pulp_href).task)
        cls.cert_guards_api.delete(cls.content_guard.pulp_href)
        delete_orphans()

    def test_read_all_repos_generic(self):
        """Ensure name is displayed when listing repositories generic."""
        repositories_api = RepositoriesApi(CoreApiClient(self.cfg.get_bindings_config()))

        response = repositories_api.list()
        self.assertNotEqual(response.count, 0)
        for repo in response.results:
            self.assertIsNotNone(repo.name)

    def test_read_all_content_generic(self):
        """Ensure href is displayed when listing content generic."""
        content_api = ContentApi(CoreApiClient(self.cfg.get_bindings_config()))

        response = content_api.list()
        self.assertNotEqual(response.count, 0)
        for content in response.results:
            self.assertIsNotNone(content.pulp_href)

    def test_read_all_content_guards_generic(self):
        """Ensure name is displayed when listing content guards generic."""
        content_guards_api = ContentguardsApi(CoreApiClient(self.cfg.get_bindings_config()))

        response = content_guards_api.list()
        self.assertNotEqual(response.count, 0)
        for content_guard in response.results:
            self.assertIsNotNone(content_guard.name)
