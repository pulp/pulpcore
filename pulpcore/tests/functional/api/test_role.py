def test_contains_permission_filter(roles_api_client):
    """Test contains_permission query parameter."""
    # Test single permission
    roles = roles_api_client.list(contains_permission=["core.change_task"])
    assert len(roles.results) > 0
    for role in roles.results:
        assert "core.change_task" in role.permissions

    # Test two permissions
    roles = roles_api_client.list(
        contains_permission=["core.change_task", "core.view_taskschedule"]
    )
    assert len(roles.results) > 0
    change_task_present = False
    view_taskschedule_present = False

    for role in roles.results:

        if "core.change_task" in role.permissions:
            change_task_present = True

        if "core.view_taskschedule" in role.permissions:
            view_taskschedule_present = True

        assert (
            "core.change_task" in role.permissions or "core.view_taskschedule" in role.permissions
        )

    assert change_task_present and view_taskschedule_present
