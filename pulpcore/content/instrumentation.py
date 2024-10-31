import time

from aiohttp import web

from pulpcore.metrics import init_otel_meter
from pulpcore.app.util import get_worker_name, normalize_http_status


def instrumentation(exporter=None, reader=None, provider=None):
    meter = init_otel_meter("pulp-content", exporter=exporter, reader=reader, provider=provider)
    request_duration_histogram = meter.create_histogram(
        name="content.request_duration",
        description="Tracks the duration of HTTP requests",
        unit="ms",
    )

    @web.middleware
    async def middleware(request, handler):
        start_time = time.time()

        try:
            response = await handler(request)
            status_code = response.status
        except web.HTTPException as exc:
            status_code = exc.status
            response = exc

        duration_ms = (time.time() - start_time) * 1000

        request_duration_histogram.record(
            duration_ms,
            attributes={
                "http.method": request.method,
                "http.status_code": normalize_http_status(status_code),
                "http.route": _get_view_request_handler_func(request),
                "worker.name": get_worker_name(),
            },
        )

        return response

    return middleware


def _get_view_request_handler_func(request):
    try:
        return request.match_info.handler.__name__
    except AttributeError:
        return "unknown"
