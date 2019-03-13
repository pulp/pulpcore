# coding=utf-8
"""Tests that CRUD distributions."""
import unittest

from itertools import permutations
from requests.exceptions import HTTPError

from pulp_smash import api, config, utils
from pulp_smash.pulp3.constants import DISTRIBUTION_PATH
from pulp_smash.pulp3.utils import gen_distribution

from pulpcore.tests.functional.utils import set_up_module as setUpModule  # noqa:F401
from pulpcore.tests.functional.utils import skip_if


class CRUDDistributionsTestCase(unittest.TestCase):
    """CRUD distributions."""

    @classmethod
    def setUpClass(cls):
        """Create class wide-variables."""
        cls.cfg = config.get_config()
        cls.client = api.Client(cls.cfg, api.json_handler)
        cls.distribution = {}

    def test_01_create_distribution(self):
        """Create a distribution."""
        body = gen_distribution()
        response_dict = self.client.post(
            DISTRIBUTION_PATH, body
        )
        dist_task = self.client.get(response_dict['task'])
        distribution_href = dist_task['created_resources'][0]
        type(self).distribution = self.client.get(distribution_href)
        for key, val in body.items():
            with self.subTest(key=key):
                self.assertEqual(self.distribution[key], val)

    @skip_if(bool, 'distribution', False)
    def test_02_create_same_name(self):
        """Try to create a second distribution with an identical name.

        See: `Pulp Smash #1055
        <https://github.com/PulpQE/pulp-smash/issues/1055>`_.
        """
        body = gen_distribution()
        body['name'] = self.distribution['name']
        with self.assertRaises(HTTPError):
            self.client.post(DISTRIBUTION_PATH, body)

    @skip_if(bool, 'distribution', False)
    def test_02_read_distribution(self):
        """Read a distribution by its _href."""
        distribution = self.client.get(self.distribution['_href'])
        for key, val in self.distribution.items():
            with self.subTest(key=key):
                self.assertEqual(distribution[key], val)

    @skip_if(bool, 'distribution', False)
    def test_02_read_distribution_with_specific_fields(self):
        """Read a distribution by its href providing specific field list.

        Permutate field list to ensure different combinations on result.
        """
        fields = ('_href', 'base_path', 'base_url', '_created')
        for field_pair in permutations(fields, 2):
            # ex: field_pair = ('_href', 'base_url)
            with self.subTest(field_pair=field_pair):
                distribution = self.client.get(
                    self.distribution['_href'],
                    params={'fields': ','.join(field_pair)}
                )
                self.assertEqual(
                    sorted(field_pair), sorted(distribution.keys())
                )

    @skip_if(bool, 'distribution', False)
    def test_02_read_distribution_without_specific_fields(self):
        """Read a distribution by its href excluding specific fields."""
        # requests doesn't allow the use of != in parameters.
        url = '{}?fields!=base_path,base_url'.format(
            self.distribution['_href']
        )
        distribution = self.client.get(url)
        response_fields = distribution.keys()
        self.assertNotIn('base_path', response_fields)
        self.assertNotIn('base_url', response_fields)

    @skip_if(bool, 'distribution', False)
    def test_02_read_distributions(self):
        """Read a distribution using query parameters.

        See: `Pulp #3082 <https://pulp.plan.io/issues/3082>`_
        """
        unique_params = (
            {'name': self.distribution['name']},
            {'base_path': self.distribution['base_path']}
        )
        for params in unique_params:
            with self.subTest(params=params):
                page = self.client.get(DISTRIBUTION_PATH, params=params)
                self.assertEqual(len(page['results']), 1)
                for key, val in self.distribution.items():
                    with self.subTest(key=key):
                        self.assertEqual(page['results'][0][key], val)

    @skip_if(bool, 'distribution', False)
    def test_03_partially_update(self):
        """Update a distribution using HTTP PATCH."""
        body = gen_distribution()
        self.client.patch(self.distribution['_href'], body)
        type(self).distribution = self.client.get(self.distribution['_href'])
        for key, val in body.items():
            with self.subTest(key=key):
                self.assertEqual(self.distribution[key], val)

    @skip_if(bool, 'distribution', False)
    def test_04_fully_update(self):
        """Update a distribution using HTTP PUT."""
        body = gen_distribution()
        self.client.put(self.distribution['_href'], body)
        type(self).distribution = self.client.get(self.distribution['_href'])
        for key, val in body.items():
            with self.subTest(key=key):
                self.assertEqual(self.distribution[key], val)

    @skip_if(bool, 'distribution', False)
    def test_05_delete(self):
        """Delete a distribution."""
        self.client.delete(self.distribution['_href'])
        with self.assertRaises(HTTPError):
            self.client.get(self.distribution['_href'])

    def test_negative_create_distribution_with_invalid_parameter(self):
        """Attempt to create distribution passing invalid parameter.

        Assert response returns an error 400 including ["Unexpected field"].
        """
        response = api.Client(self.cfg, api.echo_handler).post(
            DISTRIBUTION_PATH, gen_distribution(foo='bar')
        )
        assert response.status_code == 400
        assert response.json()['foo'] == ['Unexpected field']


class DistributionBasePathTestCase(unittest.TestCase):
    """Test possible values for ``base_path`` on a distribution.

    This test targets the following issues:

    * `Pulp #2987 <https://pulp.plan.io/issues/2987>`_
    * `Pulp #3412 <https://pulp.plan.io/issues/3412>`_
    * `Pulp Smash #906 <https://github.com/PulpQE/pulp-smash/issues/906>`_
    * `Pulp Smash #956 <https://github.com/PulpQE/pulp-smash/issues/956>`_
    """

    @classmethod
    def setUpClass(cls):
        """Create class-wide variables."""
        cls.cfg = config.get_config()
        cls.client = api.Client(cls.cfg, api.json_handler)
        body = gen_distribution()
        body['base_path'] = body['base_path'].replace('-', '/')
        response_dict = cls.client.post(DISTRIBUTION_PATH, body)
        dist_task = cls.client.get(response_dict['task'])
        distribution_href = dist_task['created_resources'][0]
        cls.distribution = cls.client.get(distribution_href)

    @classmethod
    def tearDownClass(cls):
        """Clean up resources."""
        cls.client.delete(cls.distribution['_href'])

    def test_spaces(self):
        """Test that spaces can not be part of ``base_path``."""
        self.try_create_distribution(base_path=utils.uuid4().replace('-', ' '))
        self.try_update_distribution(base_path=utils.uuid4().replace('-', ' '))

    def test_begin_slash(self):
        """Test that slash cannot be in the begin of ``base_path``."""
        self.try_create_distribution(base_path='/' + utils.uuid4())
        self.try_update_distribution(base_path='/' + utils.uuid4())

    def test_end_slash(self):
        """Test that slash cannot be in the end of ``base_path``."""
        self.try_create_distribution(base_path=utils.uuid4() + '/')
        self.try_update_distribution(base_path=utils.uuid4() + '/')

    def test_unique_base_path(self):
        """Test that ``base_path`` can not be duplicated."""
        self.try_create_distribution(base_path=self.distribution['base_path'])

    def test_overlapping_base_path(self):
        """Test that distributions can't have overlapping ``base_path``.

        See: `Pulp #2987`_.
        """
        base_path = self.distribution['base_path'].rsplit('/', 1)[0]
        self.try_create_distribution(base_path=base_path)

        base_path = '/'.join((
            self.distribution['base_path'],
            utils.uuid4().replace('-', '/'),
        ))
        self.try_create_distribution(base_path=base_path)

    def try_create_distribution(self, **kwargs):
        """Unsuccessfully create a distribution.

        Merge the given kwargs into the body of the request.
        """
        body = gen_distribution()
        body.update(kwargs)
        with self.assertRaises(HTTPError):
            self.client.post(DISTRIBUTION_PATH, body)

    def try_update_distribution(self, **kwargs):
        """Unsuccessfully update a distribution with HTTP PATCH.

        Use the given kwargs as the body of the request.
        """
        with self.assertRaises(HTTPError):
            self.client.patch(self.distribution['_href'], kwargs)
