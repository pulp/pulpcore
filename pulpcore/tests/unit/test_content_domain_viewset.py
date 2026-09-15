from pulpcore.app.viewsets.content import ContentDomainViewSet


def test_endpoint_urlpattern():
    assert ContentDomainViewSet.urlpattern() == "content/domains"
    assert ContentDomainViewSet.routable() is True


def test_access_policy_gates_on_domain_perms():
    statements = ContentDomainViewSet.DEFAULT_ACCESS_POLICY["statements"]
    assert statements == [
        {
            "action": ["list"],
            "principal": "authenticated",
            "effect": "allow",
            "condition": "has_model_or_domain_perms:core.view_content",
        }
    ]


def test_locked_role_grants_view_content():
    assert ContentDomainViewSet.LOCKED_ROLES == {
        "core.content_domain_viewer": ["core.view_content"],
    }


def test_scope_queryset_is_identity():
    sentinel = object()
    # scope_queryset must not touch the queryset (repository scoping is bypassed)
    assert ContentDomainViewSet.scope_queryset(ContentDomainViewSet(), sentinel) is sentinel
