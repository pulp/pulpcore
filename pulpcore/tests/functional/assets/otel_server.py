import asyncio
import json
import logging
import os
import sys
import threading

from aiohttp import web

from opentelemetry.proto.trace.v1.trace_pb2 import TracesData
from opentelemetry.proto.metrics.v1.metrics_pb2 import MetricsData

_logger = logging.getLogger(__name__)


class ThreadedAiohttpServer(threading.Thread):
    def __init__(self, app, host, port, ssl_ctx):
        super().__init__()
        self.app = app
        self.host = host
        self.port = port
        self.ssl_ctx = ssl_ctx
        self.loop = asyncio.new_event_loop()

    async def arun(self):
        runner = web.AppRunner(self.app)
        await runner.setup()
        site = web.TCPSite(runner, host=self.host, port=self.port, ssl_context=self.ssl_ctx)
        await site.start()
        async with self.shutdown_condition:
            await self.shutdown_condition.wait()
        await runner.cleanup()

    def run(self):
        asyncio.set_event_loop(self.loop)
        self.shutdown_condition = asyncio.Condition()
        self.loop.run_until_complete(self.arun())

    async def astop(self):
        async with self.shutdown_condition:
            self.shutdown_condition.notify_all()

    def stop(self):
        asyncio.run_coroutine_threadsafe(self.astop(), self.loop)


def _otel_collector():
    if (
        os.environ.get("PULP_OTEL_ENABLED") != "true"
        or os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT") != "http://localhost:4318"
        or os.environ.get("OTEL_EXPORTER_OTLP_PROTOCOL") != "http/protobuf"
    ):
        _logger.info("Telemetry was not configured. Exiting...")
        sys.exit(0)
    else:
        _logger.info("Booting up the otel collector server...")

    spans = []
    metrics = []

    async def _null_handler(request):
        raise web.HTTPOk()

    async def _traces_handler(request):
        traces_data = TracesData()
        traces_data.ParseFromString(await request.read())
        for resource_span in traces_data.resource_spans:
            for scope_span in resource_span.scope_spans:
                for span in scope_span.spans:
                    attrs = {
                        item.key: getattr(item.value, item.value.WhichOneof("value"))
                        for item in span.attributes
                    }
                    spans.append(attrs)
        raise web.HTTPOk()

    async def _metrics_handler(request):
        disabled_metrics = {"http.server.active_requests"}

        metrics_data = MetricsData()
        metrics_data.ParseFromString(await request.read())
        for resource_metric in metrics_data.resource_metrics:
            for scope_metric in resource_metric.scope_metrics:
                for metric in scope_metric.metrics:
                    if metric.name in disabled_metrics:
                        _logger.info("Dropping {} metric".format(metric.name))
                        break
                    translated_metric = {}
                    translated_metric["name"] = metric.name
                    translated_metric["description"] = metric.description
                    translated_metric["unit"] = metric.unit
                    metrics.append(translated_metric)
                    _logger.info("Received a {} metric meter".format(translated_metric["name"]))
        raise web.HTTPOk()

    async def _test_handler(request):
        try:
            attrs = await request.json()
        except json.decoder.JSONDecodeError:
            raise web.HTTPNotFound()

        matched_span = next(
            (span for span in spans if all((span.get(k) == v for k, v in attrs.items()))),
            None,
        )
        if matched_span:
            raise web.HTTPOk()
        else:
            raise web.HTTPNotFound()

    async def _metrics_test_handler(request):
        try:
            attrs = await request.json()
        except json.decoder.JSONDecodeError:
            raise web.HTTPNotFound()

        matched_metric = next(
            (
                metric
                for metric in metrics
                if all((metric.get(key) == value for key, value in attrs.items()))
            ),
            None,
        )
        if matched_metric:
            metrics.remove(matched_metric)
            raise web.HTTPOk()
        else:
            raise web.HTTPNotFound()

    async def _read_handler(request):
        return web.Response(text=json.dumps(metrics))

    app = web.Application()
    app.add_routes(
        [
            web.post("/v1/metrics", _metrics_handler),
            web.post("/v1/traces", _traces_handler),
            web.post("/test", _test_handler),
            web.post("/metrics_test", _metrics_test_handler),
            web.get("/read", _read_handler),
        ]
    )

    host = "127.0.0.1"
    port = 4318
    collector_server = ThreadedAiohttpServer(app, host, port, ssl_ctx=None)
    collector_server.start()


if __name__ == "__main__":
    _otel_collector()
