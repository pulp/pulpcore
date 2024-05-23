import uuid

RBAC_CONTENTGUARD_VIEW_ROLE = "core.rbaccontentguard_viewer"
RBAC_CONTENTGUARD_CREATOR_ROLE = "core.rbaccontentguard_creator"
REDIRECT_CONTENTGUARD_VIEW_ROLE = "core.contentredirectcontentguard_viewer"
REDIRECT_CONTENTGUARD_CREATOR_ROLE = "core.contentredirectcontentguard_creator"


def test_scoping(
    pulpcore_bindings,
    gen_user,
    gen_object_with_cleanup,
):
    """Tests that scoping is properly applied to detail and master views."""
    alice = gen_user(model_roles=[REDIRECT_CONTENTGUARD_VIEW_ROLE])
    bob = gen_user(model_roles=[REDIRECT_CONTENTGUARD_CREATOR_ROLE])

    gen_object_with_cleanup(
        pulpcore_bindings.ContentguardsContentRedirectApi, {"name": str(uuid.uuid4())}
    )
    with alice:
        arlist = pulpcore_bindings.ContentguardsContentRedirectApi.list()
        aclist = pulpcore_bindings.ContentguardsApi.list()
        assert arlist.count > 0 and aclist.count > 0
    with bob:
        brlist = pulpcore_bindings.ContentguardsContentRedirectApi.list()
        bclist = pulpcore_bindings.ContentguardsApi.list()
        assert brlist.count == bclist.count == 0

        gen_object_with_cleanup(
            pulpcore_bindings.ContentguardsContentRedirectApi, {"name": str(uuid.uuid4())}
        )
        brlist = pulpcore_bindings.ContentguardsContentRedirectApi.list()
        bclist = pulpcore_bindings.ContentguardsApi.list()
        assert brlist.count == bclist.count == 1


def test_master_scoping(
    pulpcore_bindings,
    gen_user,
    gen_object_with_cleanup,
):
    """Tests that master views will scope off each child's scoping."""
    alice = gen_user(model_roles=[REDIRECT_CONTENTGUARD_VIEW_ROLE, RBAC_CONTENTGUARD_VIEW_ROLE])
    bob = gen_user(model_roles=[REDIRECT_CONTENTGUARD_CREATOR_ROLE, RBAC_CONTENTGUARD_CREATOR_ROLE])

    gen_object_with_cleanup(
        pulpcore_bindings.ContentguardsContentRedirectApi, {"name": str(uuid.uuid4())}
    )
    gen_object_with_cleanup(pulpcore_bindings.ContentguardsRbacApi, {"name": str(uuid.uuid4())})

    with alice:
        aclist = pulpcore_bindings.ContentguardsApi.list()
        assert aclist.count >= 2
    with bob:
        bclist = pulpcore_bindings.ContentguardsApi.list()
        assert bclist.count == 0
        gen_object_with_cleanup(
            pulpcore_bindings.ContentguardsContentRedirectApi, {"name": str(uuid.uuid4())}
        )
        gen_object_with_cleanup(pulpcore_bindings.ContentguardsRbacApi, {"name": str(uuid.uuid4())})
        bclist = pulpcore_bindings.ContentguardsApi.list()
        assert bclist.count >= 2
    with alice:
        aclist = pulpcore_bindings.ContentguardsApi.list()
        assert aclist.count >= 4
