import pytest

from django.test import RequestFactory
from django.http import HttpResponse

from pulpcore.middleware import DjangoMetricsMiddleware


@pytest.fixture
def run_middleware():
    def _run_middleware(provider):
        factory = RequestFactory()
        request = factory.get("/")

        response = HttpResponse()
        response.status_code = 200

        middleware = DjangoMetricsMiddleware(lambda req: response)

        meter = provider.get_meter("pulp.metrics")
        middleware._set_histogram(meter)

        middleware(request)

    return _run_middleware


def test_instrumentation(meter_provider, run_middleware):
    run_middleware(meter_provider)
