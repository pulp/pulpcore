import pytest
from random import sample
from uuid import uuid4

from pulpcore.client.pulpcore.exceptions import ApiException


def extract_pk(href):
    """Simulate what pulpcore.app.util.extract_pk does."""
    parts = href.split("/")
    return parts[-2]


@pytest.fixture
def gen_rbac_and_redirect_guards(
    redirect_contentguard_api_client,
    rbac_contentguard_api_client,
    gen_object_with_cleanup,
):
    def _generate(number=5):
        rbacs = []
        redis = []
        for _ in range(number):
            rbacs.append(
                gen_object_with_cleanup(rbac_contentguard_api_client, {"name": str(uuid4())})
            )
            redis.append(
                gen_object_with_cleanup(redirect_contentguard_api_client, {"name": str(uuid4())})
            )
        return rbacs, redis

    return _generate


@pytest.mark.parallel
@pytest.mark.parametrize(
    "filter,f,exception_message",
    [("pulp_id__in", extract_pk, "Enter a valid UUID"), ("pulp_href__in", str, "URI not valid")],
)
def test_pulp_id_href_filter(
    filter,
    f,
    exception_message,
    content_guards_api_client,
    redirect_contentguard_api_client,
    rbac_contentguard_api_client,
    gen_rbac_and_redirect_guards,
):
    """Tests pulp_href__in and pulp_id__in filters."""
    rbacs, redis = gen_rbac_and_redirect_guards()
    rbac_extracted = [f(cg.pulp_href) for cg in rbacs]
    redi_extracted = [f(cg.pulp_href) for cg in redis]

    rbac_sample = sample(rbac_extracted, 3)
    redi_sample = sample(redi_extracted, 3)

    rbac_results = rbac_contentguard_api_client.list(**{filter: rbac_sample})
    assert rbac_results.count == 3
    assert set(rbac_sample) == {f(cg.pulp_href) for cg in rbac_results.results}

    redi_results = redirect_contentguard_api_client.list(**{filter: redi_sample})
    assert redi_results.count == 3
    assert set(redi_sample) == {f(cg.pulp_href) for cg in redi_results.results}

    # Test that generic endpoint can return both
    results = content_guards_api_client.list(**{filter: rbac_sample + redi_sample})
    assert results.count == 6
    assert set(redi_sample + rbac_sample) == {f(cg.pulp_href) for cg in results.results}

    # Test swapping rbac & redirect return 0
    rbac_results = rbac_contentguard_api_client.list(**{filter: redi_sample})
    assert rbac_results.count == 0

    redi_results = redirect_contentguard_api_client.list(**{filter: rbac_sample})
    assert redi_results.count == 0

    # Test that filter fails when not a valid type
    with pytest.raises(ApiException) as exc:
        content_guards_api_client.list(**{filter: ["hello"]})

    assert exc.value.status == 400
    assert exception_message in exc.value.body
