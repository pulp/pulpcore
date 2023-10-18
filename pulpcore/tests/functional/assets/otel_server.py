import asyncio
import json
import logging
import os
import sys
import threading

from aiohttp import web

from opentelemetry.proto.trace.v1.trace_pb2 import TracesData


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
        logging.info("Telemetry was not configured. Exiting...")
        sys.exit(0)
    else:
        logging.info("Booting up the otel collector server...")

    spans = []

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

    app = web.Application()
    app.add_routes(
        [
            web.post("/v1/metrics", _null_handler),
            web.post("/v1/traces", _traces_handler),
            web.post("/test", _test_handler),
        ]
    )

    host = "127.0.0.1"
    port = 4318
    collector_server = ThreadedAiohttpServer(app, host, port, ssl_ctx=None)
    collector_server.start()


if __name__ == "__main__":
    _otel_collector()
