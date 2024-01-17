import pytest

try:
    from pulpcore.client.pulp_certguard import (
        ApiClient,
        ContentguardsX509Api,
        ContentguardsRhsmApi,
    )
except ImportError:
    pass
else:

    @pytest.fixture(scope="session")
    def pulp_certguard_client(_api_client_set, bindings_cfg):
        """Api client for certguards."""
        api_client = ApiClient(bindings_cfg)
        _api_client_set.add(api_client)
        yield api_client
        _api_client_set.remove(api_client)

    @pytest.fixture(scope="session")
    def x509_content_guards_api_client(pulp_certguard_client):
        """Api for x509 content guards."""
        return ContentguardsX509Api(pulp_certguard_client)

    @pytest.fixture(scope="session")
    def rhsm_content_guards_api_client(pulp_certguard_client):
        """Api for rhsm content guards."""
        return ContentguardsRhsmApi(pulp_certguard_client)
