import asyncio
import pytest

from pulpcore.tests.functional.utils import get_response


@pytest.mark.parallel
def test_anonymous_access_to_root(pulp_api_v3_url):
    response = asyncio.run(get_response(pulp_api_v3_url))
    assert response.ok
