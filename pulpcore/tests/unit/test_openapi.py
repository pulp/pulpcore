import pytest

from pulpcore.app.viewsets.repository import (
    RepositoryStagingViewSet,
    RepositoryVersionViewSet,
    RepositoryViewSet,
)
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
            "/repositories/{repository_pk}/staging/",
            RepositoryStagingViewSet,
            "list",
            "{repository_href}staging/",
            id="nested-staging-collection",
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
