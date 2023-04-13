import pytest
from random import sample
from uuid import uuid4

from pulpcore.client.pulpcore.exceptions import ApiException, ApiTypeError


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


@pytest.mark.parallel
def test_pulp_type_filter(
    content_guards_api_client,
    redirect_contentguard_api_client,
    rbac_contentguard_api_client,
    gen_rbac_and_redirect_guards,
):
    """Tests the pulp_type__in filter."""
    gen_rbac_and_redirect_guards()

    # Test filtering by one pulp_type
    rbac_result = content_guards_api_client.list(pulp_type__in=["core.rbac"])
    assert rbac_result.count >= 5
    for c in rbac_result.results:
        assert "core/rbac" in c.pulp_href

    redirect_result = content_guards_api_client.list(pulp_type__in=["core.content_redirect"])
    assert redirect_result.count >= 5
    for c in redirect_result.results:
        assert "core/content_redirect" in c.pulp_href

    # Test filtering by multiple pulp_types
    together_result = content_guards_api_client.list(
        pulp_type__in=["core.rbac", "core.content_redirect"]
    )
    assert together_result.count >= 10
    for c in together_result.results:
        assert "core/rbac" in c.pulp_href or "core/content_redirect" in c.pulp_href

    # Test filtering by invalid pulp_type
    with pytest.raises(ApiException) as exc:
        content_guards_api_client.list(pulp_type__in=["i.invalid"])

    assert exc.value.status == 400
    assert "Select a valid choice. i.invalid is not one of the available choices." in exc.value.body

    # Test filter does not exist on child viewsets
    with pytest.raises(ApiTypeError) as exc:
        rbac_contentguard_api_client.list(pulp_type__in=["core.rbac"])

    assert "Got an unexpected keyword argument 'pulp_type__in'" in str(exc.value)

    with pytest.raises(ApiTypeError) as exc:
        redirect_contentguard_api_client.list(pulp_type__in=["core.content_redirect"])

    assert "Got an unexpected keyword argument 'pulp_type__in'" in str(exc.value)
