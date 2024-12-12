def test_correlation_id(cid, pulpcore_bindings, monitor_task):
    """Test that a correlation can be passed as a header and logged."""
    response = pulpcore_bindings.OrphansCleanupApi.cleanup_with_http_info({})
    if isinstance(response, tuple):
        # old bindings
        data, _, headers = response
    else:
        # new bindings
        data = response.data
        headers = response.headers
    task = monitor_task(data.task)
    assert headers["Correlation-ID"] == cid
    assert task.logging_cid == cid
