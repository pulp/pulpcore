import pytest

from pulpcore.app.viewsets.repository import RepositoryVersionViewSet, RepositoryViewSet
from pulpcore.openapi import PulpSchemaGenerator


@pytest.mark.parametrize(
    ("path", "viewset_class", "action", "expected"),
    [
        pytest.param(
            "/repositories/", RepositoryViewSet, "list", "/repositories/", id="collection"
        ),
        pytest.param(
            "/repositories/{pulp_id}/",
            RepositoryViewSet,
            "retrieve",
            "{repository_href}",
            id="detail",
        ),
        pytest.param(
            "/repositories/{pulp_id}/staging/",
            RepositoryViewSet,
            "staging",
            "{repository_href}staging/",
            id="detail-action",
        ),
        pytest.param(
            "/repositories/{pulp_id}/staging/{relative_path}/",
            RepositoryViewSet,
            "staging_path",
            "{repository_href}staging/{relative_path}/",
            id="detail-action-with-path-parameter",
        ),
        pytest.param(
            "/repositories/{repository_pk}/versions/",
            RepositoryVersionViewSet,
            "list",
            "{repository_href}versions/",
            id="nested-collection",
        ),
        pytest.param(
            "/repositories/{repository_pk}/versions/{number}/",
            RepositoryVersionViewSet,
            "retrieve",
            "{repositories_repository_version_href}",
            id="nested-detail",
        ),
    ],
)
def test_convert_endpoint_path_params(path, viewset_class, action, expected):
    viewset = viewset_class()
    viewset.action = action

    converted = PulpSchemaGenerator().convert_endpoint_path_params(path, viewset, None)

    assert converted == expected
