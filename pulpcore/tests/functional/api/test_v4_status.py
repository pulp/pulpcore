import pytest
import requests
from django.conf import settings


@pytest.mark.parallel
@pytest.mark.skipif(
    not settings.ENABLE_V4_API,
    reason="Test is pointless if V4 isn't enabled",
)
@pytest.mark.parametrize(
    "version,expect_pass,new_fields",
    [("v3", True, False), ("v4", True, True), ("v5", False, False)],
)
def test_v4_status(version, expect_pass, new_fields, pulp_api_v3_url, pulp_settings):
    v3_status_url = f"{pulp_api_v3_url}status/"
    status_url = v3_status_url.replace("v3", version)
    response = requests.get(status_url)
    if expect_pass:
        assert response.status_code == 200
        if new_fields:
            status_dict = response.json()
            assert "pulp_api_version" in status_dict
            assert status_dict["pulp_api_version"] == version
            assert "supported_pulp_api_versions" in status_dict
    else:
        assert response.status_code == 404
        assert response.json()["detail"] == "Invalid version in URL path."
