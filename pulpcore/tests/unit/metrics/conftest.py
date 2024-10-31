import pytest

from opentelemetry.sdk.metrics.export import InMemoryMetricReader
from opentelemetry.sdk.metrics import MeterProvider


@pytest.fixture
def meter_provider():
    reader = InMemoryMetricReader()
    provider = MeterProvider(metric_readers=[reader])

    yield provider

    data = reader.get_metrics_data()
    metrics = data.resource_metrics[0].scope_metrics[0].metrics
    assert len(metrics) == 1

    point = metrics[0].data.data_points[0]
    assert point.count == 1
    assert point.sum > 0
    assert point.attributes["http.status_code"] == "2xx"
    assert point.attributes["http.method"] == "GET"
