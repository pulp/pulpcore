import pytest

from pulpcore.app.jq_utils import compile_safe_jq

DATA = {
    "sub": "user1",
    "org_id": "org1",
    "roles": [{"name": "reader", "active": True}, {"name": "writer", "active": False}],
}

MALICIOUS_FILTERS = [
    "env",
    "$ENV",
    "env.SECRET_KEY",
    "$ENV.SECRET_KEY",
    "env | .",
    "def getenv: env; getenv",
    "builtins",
    'env // "leaked"',
    'try env catch "leaked"',
    ".. , env",
    "label $x | env",
    'env | to_entries | map(.value) | join(",")',
]


@pytest.mark.parametrize("jq_filter", MALICIOUS_FILTERS)
def test_environment_is_not_reachable(jq_filter, monkeypatch):
    """Filters must not be able to read the environment of the running process."""
    monkeypatch.setenv("PULP_TEST_SECRET", "topsecret")

    result = compile_safe_jq(jq_filter).input_value(DATA).first()

    assert "topsecret" not in repr(result)


@pytest.mark.parametrize(
    "jq_filter,expected",
    [
        (".sub", "user1"),
        ('.sub // ""', "user1"),
        (".roles[] | select(.active) | .name", "reader"),
        (".roles | map(.name)", ["reader", "writer"]),
        (r'"\(.org_id)|\(.sub)"', "org1|user1"),
        (".roles[0].name", "reader"),
        (".missing?", None),
    ],
)
def test_regular_filters_still_work(jq_filter, expected):
    """Shadowing the environment must not restrict the rest of the jq language."""
    result = compile_safe_jq(jq_filter).input_value(DATA).first()

    assert result == expected


def test_invalid_filter_raises_value_error():
    with pytest.raises(ValueError):
        compile_safe_jq("def broken:").input_value(DATA).first()
