from pulp_smash.pulp3.bindings import monitor_task


def test_correlation_id(cid, tasks_api_client, orphans_cleanup_api_client):
    """Test that a correlation can be passed as a header and logged."""
    response, status, headers = orphans_cleanup_api_client.cleanup_with_http_info({})
    monitor_task(response.task)
    task = tasks_api_client.read(response.task)
    assert headers["Correlation-ID"] == cid
    assert task.logging_cid == cid
