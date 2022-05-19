import uuid

RBAC_CONTENTGUARD_VIEW_ROLE = "core.rbaccontentguard_viewer"
RBAC_CONTENTGUARD_CREATOR_ROLE = "core.rbaccontentguard_creator"
REDIRECT_CONTENTGUARD_VIEW_ROLE = "core.contentredirectcontentguard_viewer"
REDIRECT_CONTENTGUARD_CREATOR_ROLE = "core.contentredirectcontentguard_creator"


def test_scoping(
    content_guards_api_client,
    redirect_contentguard_api_client,
    gen_user,
    gen_object_with_cleanup,
):
    """Tests that scoping is properly applied to detail and master views."""
    alice = gen_user(model_roles=[REDIRECT_CONTENTGUARD_VIEW_ROLE])
    bob = gen_user(model_roles=[REDIRECT_CONTENTGUARD_CREATOR_ROLE])

    gen_object_with_cleanup(redirect_contentguard_api_client, {"name": str(uuid.uuid4())})
    with alice:
        arlist = redirect_contentguard_api_client.list()
        aclist = content_guards_api_client.list()
        assert arlist.count > 0 and aclist.count > 0
    with bob:
        brlist = redirect_contentguard_api_client.list()
        bclist = content_guards_api_client.list()
        assert brlist.count == bclist.count == 0

        gen_object_with_cleanup(redirect_contentguard_api_client, {"name": str(uuid.uuid4())})
        brlist = redirect_contentguard_api_client.list()
        bclist = content_guards_api_client.list()
        assert brlist.count == bclist.count == 1


def test_master_scoping(
    content_guards_api_client,
    redirect_contentguard_api_client,
    rbac_contentguard_api_client,
    gen_user,
    gen_object_with_cleanup,
):
    """Tests that master views will scope off each child's scoping."""
    alice = gen_user(model_roles=[REDIRECT_CONTENTGUARD_VIEW_ROLE, RBAC_CONTENTGUARD_VIEW_ROLE])
    bob = gen_user(model_roles=[REDIRECT_CONTENTGUARD_CREATOR_ROLE, RBAC_CONTENTGUARD_CREATOR_ROLE])

    gen_object_with_cleanup(redirect_contentguard_api_client, {"name": str(uuid.uuid4())})
    gen_object_with_cleanup(rbac_contentguard_api_client, {"name": str(uuid.uuid4())})

    with alice:
        aclist = content_guards_api_client.list()
        assert aclist.count >= 2
    with bob:
        bclist = content_guards_api_client.list()
        assert bclist.count == 0
        gen_object_with_cleanup(redirect_contentguard_api_client, {"name": str(uuid.uuid4())})
        gen_object_with_cleanup(rbac_contentguard_api_client, {"name": str(uuid.uuid4())})
        bclist = content_guards_api_client.list()
        assert bclist.count >= 2
    with alice:
        aclist = content_guards_api_client.list()
        assert aclist.count >= 4
