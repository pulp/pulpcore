import requests
import pytest


@pytest.mark.parallel
def test_anonymous_access_to_root(pulp_api_v3_url):
    response = requests.get(pulp_api_v3_url)
    assert response.ok
