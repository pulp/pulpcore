# coding=utf-8
"""Tests that perform actions over publications."""
import unittest

from itertools import permutations
from requests.exceptions import HTTPError

from pulp_smash import api, config
from pulp_smash.pulp3.constants import (
    DISTRIBUTION_PATH,
    PUBLICATIONS_PATH,
    REPO_PATH
)
from pulp_smash.pulp3.utils import (
    gen_distribution,
    gen_publisher,
    gen_repo,
    publish,
    sync
)

from pulpcore.tests.functional.api.utils import parse_date_from_string
from pulpcore.tests.functional.api.using_plugin.constants import (
    FILE_PUBLISHER_PATH,
    FILE_REMOTE_PATH
)
from pulpcore.tests.functional.api.using_plugin.utils import (
    gen_file_remote,
    skip_if
)
from pulpcore.tests.functional.api.using_plugin.utils import set_up_module as setUpModule  # noqa


class PublicationsTestCase(unittest.TestCase):
    """Perform actions over publications."""

    @classmethod
    def setUpClass(cls):
        """Create class-wide variables."""
        cls.cfg = config.get_config()
        cls.client = api.Client(cls.cfg, api.page_handler)
        cls.remote = {}
        cls.publication = {}
        cls.publisher = {}
        cls.repo = {}
        try:
            cls.repo.update(cls.client.post(REPO_PATH, gen_repo()))
            body = gen_file_remote()
            cls.remote.update(cls.client.post(FILE_REMOTE_PATH, body))
            cls.publisher.update(
                cls.client.post(FILE_PUBLISHER_PATH, gen_publisher())
            )
            sync(cls.cfg, cls.remote, cls.repo)
        except Exception:
            cls.tearDownClass()
            raise

    @classmethod
    def tearDownClass(cls):
        """Clean class-wide variables."""
        for resource in (cls.remote, cls.publisher, cls.repo):
            if resource:
                cls.client.delete(resource['_href'])

    def test_01_create_publication(self):
        """Create a publication."""
        self.publication.update(
            publish(self.cfg, self.publisher, self.repo)
        )

    @skip_if(bool, 'publication', False)
    def test_02_read_publication(self):
        """Read a publication by its href."""
        publication = self.client.get(self.publication['_href'])
        for key, val in self.publication.items():
            with self.subTest(key=key):
                self.assertEqual(publication[key], val)

    @skip_if(bool, 'publication', False)
    def test_02_read_publication_with_specific_fields(self):
        """Read a publication by its href providing specific field list.

        Permutate field list to ensure different combinations on result.
        """
        fields = ('_href', '_created', '_distributions', 'publisher')
        for field_pair in permutations(fields, 2):
            # ex: field_pair = ('_href', '_created)
            with self.subTest(field_pair=field_pair):
                publication = self.client.get(
                    self.publication['_href'],
                    params={'fields': ','.join(field_pair)}
                )
                self.assertEqual(
                    sorted(field_pair), sorted(publication.keys())
                )

    @skip_if(bool, 'publication', False)
    def test_02_read_publication_without_specific_fields(self):
        """Read a publication by its href excluding specific fields."""
        # requests doesn't allow the use of != in parameters.
        url = '{}?fields!=_distributions'.format(self.publication['_href'])
        publication = self.client.get(url)
        self.assertNotIn('_distributions', publication.keys())

    @skip_if(bool, 'publication', False)
    def test_02_read_publications(self):
        """Read a publication by its repository version."""
        publications = self.client.get(PUBLICATIONS_PATH, params={
            'repository_version': self.repo['_href']
        })
        self.assertEqual(len(publications), 1, publications)
        for key, val in self.publication.items():
            with self.subTest(key=key):
                self.assertEqual(publications[0][key], val)

    @skip_if(bool, 'publication', False)
    def test_03_read_publications(self):
        """Read a publication by its publisher."""
        publications = self.client.get(PUBLICATIONS_PATH, params={
            'publisher': self.publisher['_href']
        })
        self.assertEqual(len(publications), 1, publications)
        for key, val in self.publication.items():
            with self.subTest(key=key):
                self.assertEqual(publications[0][key], val)

    @skip_if(bool, 'publication', False)
    def test_04_read_publications(self):
        """Read a publication by its created time."""
        publications = self.client.get(PUBLICATIONS_PATH, params={
            '_created': self.publication['_created']
        })
        self.assertEqual(len(publications), 1, publications)
        for key, val in self.publication.items():
            with self.subTest(key=key):
                self.assertEqual(publications[0][key], val)

    @skip_if(bool, 'publication', False)
    def test_05_read_publications(self):
        """Read a publication by its distribution."""
        body = gen_distribution()
        body['publication'] = self.publication['_href']
        response_dict = self.client.post(DISTRIBUTION_PATH, body)
        dist_task = self.client.get(response_dict['task'])
        distribution_href = dist_task['created_resources'][0]
        distribution = self.client.get(distribution_href)
        self.addCleanup(self.client.delete, distribution['_href'])

        self.publication.update(self.client.get(self.publication['_href']))
        publications = self.client.get(PUBLICATIONS_PATH, params={
            'distributions': distribution['_href']
        })
        self.assertEqual(len(publications), 1, publications)
        for key, val in self.publication.items():
            with self.subTest(key=key):
                self.assertEqual(publications[0][key], val)

    @skip_if(bool, 'publication', False)
    def test_06_publication_create_order(self):
        """Assert that publications are ordered by created time.

        This test targets the following issues:

        * `Pulp Smash #954 <https://github.com/PulpQE/pulp-smash/issues/954>`_
        * `Pulp #3576 <https://pulp.plan.io/issues/3576>`_
        """
        # Create more 2 publications for the same repo
        for _ in range(2):
            publish(self.cfg, self.publisher, self.repo)

        # Read publications
        publications = self.client.get(
            PUBLICATIONS_PATH,
            params={'publisher': self.publisher['_href']}
        )
        self.assertEqual(len(publications), 3)

        # Assert publications are ordered by _created field in descending order
        for i, publication in enumerate(publications[:-1]):
            self.assertGreater(
                parse_date_from_string(publication['_created']),  # Current
                parse_date_from_string(publications[i + 1]['_created'])  # Prev
            )

    @skip_if(bool, 'publication', False)
    def test_07_delete(self):
        """Delete a publication."""
        self.client.delete(self.publication['_href'])
        with self.assertRaises(HTTPError):
            self.client.get(self.publication['_href'])

    def test_negative_create_file_remote_with_invalid_parameter(self):
        """Attempt to create file remote passing invalid parameter.

        Assert response returns an error 400 including ["Unexpected field"].
        """
        response = api.Client(self.cfg, api.echo_handler).post(
            FILE_REMOTE_PATH, gen_file_remote(foo='bar')
        )
        assert response.status_code == 400
        assert response.json()['foo'] == ['Unexpected field']

    def test_negative_create_file_publisher_with_invalid_parameter(self):
        """Attempt to create file publisher passing invalid parameter.

        Assert response returns an error 400 including ["Unexpected field"].
        """
        response = api.Client(self.cfg, api.echo_handler).post(
            FILE_PUBLISHER_PATH, gen_publisher(foo='bar')
        )
        assert response.status_code == 400
        assert response.json()['foo'] == ['Unexpected field']
