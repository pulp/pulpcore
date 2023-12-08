def test_correlation_id(cid, pulpcore_bindings, monitor_task):
    """Test that a correlation can be passed as a header and logged."""
    response, status, headers = pulpcore_bindings.OrphansCleanupApi.cleanup_with_http_info({})
    monitor_task(response.task)
    task = pulpcore_bindings.TasksApi.read(response.task)
    assert headers["Correlation-ID"] == cid
    assert task.logging_cid == cid
