import pytest

from pulpcore.tests.functional.utils import BindingsNamespace


@pytest.fixture(scope="session")
def certguard_bindings(_api_client_set, bindings_cfg):
    """Api client for certguards."""
    from pulpcore.client import pulp_certguard as certguard_bindings_module

    api_client = certguard_bindings_module.ApiClient(bindings_cfg)
    _api_client_set.add(api_client)
    yield BindingsNamespace(certguard_bindings_module, api_client)
    _api_client_set.remove(api_client)


@pytest.fixture(scope="session")
def x509_content_guards_api_client(certguard_bindings):
    """Api for x509 content guards."""
    return certguard_bindings.ContentguardsX509Api


@pytest.fixture(scope="session")
def rhsm_content_guards_api_client(certguard_bindings):
    """Api for rhsm content guards."""
    return certguard_bindings.ContentguardsRhsmApi
