import pytest
import random
import uuid

from pulpcore.client.pulpcore.exceptions import ApiException, ApiTypeError


# Warning: Do not use HEX digits here!
NAMES = (
    "GGGG",
    "GGHH",
    "gggg",
    "GgHh",
    "áàâãäæÁÀÂÃÄçÇéèêëíìĩïóòôõöúùûũüßþ",
)


def extract_pk(href):
    """Simulate what pulpcore.app.util.extract_pk does."""
    parts = href.split("/")
    return parts[-2]


@pytest.fixture(scope="class")
def rbac_and_redirect_guards(
    pulpcore_bindings,
    gen_object_with_cleanup,
):
    prefix = str(uuid.uuid4())
    rbacs = []
    redis = []
    for name in NAMES:
        rbacs.append(
            gen_object_with_cleanup(
                pulpcore_bindings.ContentguardsRbacApi, {"name": prefix + "-" + name}
            )
        )
        redis.append(
            gen_object_with_cleanup(
                pulpcore_bindings.ContentguardsContentRedirectApi, {"name": prefix + "+" + name}
            )
        )
    return prefix, rbacs, redis


class TestFilter:
    @pytest.mark.parallel
    @pytest.mark.parametrize(
        "filter,f,exception_message",
        [
            ("pulp_id__in", extract_pk, "Enter a valid UUID"),
            ("pulp_href__in", str, "URI not valid"),
        ],
    )
    def test_pulp_id_href_filter(
        self,
        filter,
        f,
        exception_message,
        pulpcore_bindings,
        rbac_and_redirect_guards,
    ):
        """Tests pulp_href__in and pulp_id__in filters."""
        prefix, rbacs, redis = rbac_and_redirect_guards
        rbac_extracted = [f(cg.pulp_href) for cg in rbacs]
        redi_extracted = [f(cg.pulp_href) for cg in redis]

        rbac_sample = random.sample(rbac_extracted, 3)
        redi_sample = random.sample(redi_extracted, 3)

        rbac_results = pulpcore_bindings.ContentguardsRbacApi.list(**{filter: rbac_sample})
        assert rbac_results.count == 3
        assert set(rbac_sample) == {f(cg.pulp_href) for cg in rbac_results.results}

        redi_results = pulpcore_bindings.ContentguardsContentRedirectApi.list(
            **{filter: redi_sample}
        )
        assert redi_results.count == 3
        assert set(redi_sample) == {f(cg.pulp_href) for cg in redi_results.results}

        # Test that generic endpoint can return both
        results = pulpcore_bindings.ContentguardsApi.list(**{filter: rbac_sample + redi_sample})
        assert results.count == 6
        assert set(redi_sample + rbac_sample) == {f(cg.pulp_href) for cg in results.results}

        # Test swapping rbac & redirect return 0
        rbac_results = pulpcore_bindings.ContentguardsRbacApi.list(**{filter: redi_sample})
        assert rbac_results.count == 0

        redi_results = pulpcore_bindings.ContentguardsContentRedirectApi.list(
            **{filter: rbac_sample}
        )
        assert redi_results.count == 0

        # test out empty list
        redi_results = pulpcore_bindings.ContentguardsContentRedirectApi.list(**{filter: []})
        assert redi_results.count == 0

        # Test that filter fails when not a valid type
        with pytest.raises(ApiException) as exc:
            pulpcore_bindings.ContentguardsApi.list(**{filter: ["hello"]})

        assert exc.value.status == 400
        assert exception_message in exc.value.body

    @pytest.mark.parallel
    def test_pulp_type_filter(
        self,
        pulpcore_bindings,
        rbac_and_redirect_guards,
    ):
        """Tests the pulp_type__in filter."""
        prefix = rbac_and_redirect_guards[0]
        # Test filtering by one pulp_type
        rbac_result = pulpcore_bindings.ContentguardsApi.list(
            name__startswith=prefix, pulp_type__in=["core.rbac"]
        )
        assert rbac_result.count == 5
        for c in rbac_result.results:
            assert "core/rbac" in c.pulp_href

        redirect_result = pulpcore_bindings.ContentguardsApi.list(
            name__startswith=prefix, pulp_type__in=["core.content_redirect"]
        )
        assert redirect_result.count == 5
        for c in redirect_result.results:
            assert "core/content_redirect" in c.pulp_href

        # Test filtering by multiple pulp_types
        together_result = pulpcore_bindings.ContentguardsApi.list(
            name__startswith=prefix, pulp_type__in=["core.rbac", "core.content_redirect"]
        )
        assert together_result.count == 10
        for c in together_result.results:
            assert "core/rbac" in c.pulp_href or "core/content_redirect" in c.pulp_href

        # Test filtering by invalid pulp_type
        with pytest.raises(ApiException) as exc:
            pulpcore_bindings.ContentguardsApi.list(pulp_type__in=["i.invalid"])

        assert exc.value.status == 400
        assert (
            "Select a valid choice. i.invalid is not one of the available choices."
            in exc.value.body
        )

        # Test filter does not exist on child viewsets
        with pytest.raises(ApiTypeError) as exc:
            pulpcore_bindings.ContentguardsRbacApi.list(pulp_type__in=["core.rbac"])

        assert "Got an unexpected keyword argument 'pulp_type__in'" in str(exc.value)

        with pytest.raises(ApiTypeError) as exc:
            pulpcore_bindings.ContentguardsContentRedirectApi.list(
                pulp_type__in=["core.content_redirect"]
            )

        assert "Got an unexpected keyword argument 'pulp_type__in'" in str(exc.value)

    @pytest.mark.parallel
    @pytest.mark.parametrize(
        "q,count",
        [
            pytest.param(*data, id=data[0])
            for data in [
                ("pulp_type__in='core.rbac'", 5),
                ('NOT pulp_type="core.rbac"', 5),
                ("pulp_type__in=core.rbac,core.content_redirect", 10),
                ('pulp_type="core.rbac" OR pulp_type="core.content_redirect"', 10),
                ('pulp_type="core.rbac" AND name__contains=GGGG', 1),
                ('pulp_type="core.rbac" AND name__iexact={prefix}-gGgG', 2),
                ('pulp_type="core.rbac" AND name__icontains=gg AND NOT name__contains=HH', 3),
                ('NOT (pulp_type="core.rbac" AND name__icontains=gGgG)', 8),
                ('pulp_type="core.rbac" AND name__contains="{4}"', 1),
                ('pulp_type="core.rbac" AND NOT name__contains="{4}"', 4),
                ('pulp_type="core.rbac" AND(   name__icontains=gh OR name__contains="{4}")', 3),
                ('pulp_type="core.rbac" OR name__icontains=gh OR name__contains="{4}"', 8),
            ]
        ],
    )
    def test_q_filter_valid(
        self,
        q,
        count,
        pulpcore_bindings,
        rbac_and_redirect_guards,
    ):
        """Tests the "q" filter."""
        prefix = rbac_and_redirect_guards[0]

        result = pulpcore_bindings.ContentguardsApi.list(
            name__startswith=prefix, q=q.format(*NAMES, prefix=prefix)
        )
        assert result.count == count

    @pytest.mark.parallel
    @pytest.mark.parametrize(
        "q,exception_message",
        [
            pytest.param(*data, id=data[0])
            for data in [
                ('pulp_type_in="core.rbac"', '{"q":["Filter \'pulp_type_in\' does not exist."]}'),
                (
                    'pulp_type="core.foo"',
                    '{"q":["{\\"pulp_type\\": [{\\"message\\": \\"Select a valid choice. core.foo is not one of the available choices.\\", \\"code\\": \\"invalid_choice\\"}]}"]}',  # noqa
                ),
                (
                    'pulp_type__in="core.rbac,core.foo"',
                    '{"q":["{\\"pulp_type__in\\": [{\\"message\\": \\"Select a valid choice. core.foo is not one of the available choices.\\", \\"code\\": \\"invalid_choice\\"}]}"]}',  # noqa
                ),
                ('name="test" and', '{"q":["Syntax error in expression."]}'),
                ('name="test" AND', '{"q":["Syntax error in expression."]}'),
                ('name="test" AND (name="test2"', '{"q":["Syntax error in expression."]}'),
                (
                    'name="test1" OR name="test2" OR name="test3" OR name="test4" OR name="test5" OR name="test6" OR name="test7" OR name="test8"',  # noqa
                    '{"q":["Filter expression exceeds allowed complexity."]}',
                ),
                (
                    '(name="test1" OR name="test2") OR name="test3" OR name="test4" OR name="test5" OR name="test6" OR name="test7"',  # noqa
                    '{"q":["Filter expression exceeds allowed complexity."]}',
                ),
                (
                    '(name="test1" OR NOT name="test2") OR name="test3" OR name="test4" OR name="test5" OR name="test6"',  # noqa
                    '{"q":["Filter expression exceeds allowed complexity."]}',
                ),
            ]
        ],
    )
    def test_q_filter_invalid(
        self,
        q,
        exception_message,
        pulpcore_bindings,
    ):
        """Tests the "q" filter with invalid expressions."""

        with pytest.raises(ApiException) as exc_info:
            pulpcore_bindings.ContentguardsApi.list(q=q.format(*NAMES))
        assert exc_info.value.status == 400
        assert exc_info.value.body == exception_message
