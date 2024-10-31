from functools import lru_cache

from django.conf import settings

from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.sdk.resources import Resource

from pulpcore.app.util import get_domain, get_worker_name


@lru_cache(maxsize=1)
def init_otel_meter(service_name, exporter=None, reader=None, provider=None):
    exporter = exporter or OTLPMetricExporter()
    reader = reader or PeriodicExportingMetricReader(exporter)
    resource = Resource(attributes={"service.name": service_name})
    provider = provider or MeterProvider(metric_readers=[reader], resource=resource)
    return provider.get_meter("pulp.metrics")


class MetricsEmitter:
    """
    A builder class that initializes an emitter.

    If Open Telemetry is enabled, the builder configures a real emitter capable of sending data to
    the collector. Otherwise, a no-op emitter is initialized. The real emitter may utilize the
    global settings to send metrics.

    By default, the emitter sends data to the collector every 60 seconds. Adjust the environment
    variable OTEL_METRIC_EXPORT_INTERVAL accordingly if needed.
    """

    class _NoopEmitter:
        def __call__(self, *args, **kwargs):
            return self

        def __getattr__(self, *args, **kwargs):
            return self

    @classmethod
    def build(cls, *args, **kwargs):
        if settings.OTEL_ENABLED and settings.DOMAIN_ENABLED:
            return cls(*args, **kwargs)
        else:
            return cls._NoopEmitter()


class ArtifactsSizeCounter(MetricsEmitter):
    def __init__(self):
        self.meter = init_otel_meter("pulp-content")
        self.counter = self.meter.create_counter(
            "artifacts.size.counter",
            unit="Bytes",
            description="Counts the size of served artifacts",
        )

    def add(self, amount):
        attributes = {
            "domain_name": get_domain().name,
            "worker_process": get_worker_name(),
        }
        self.counter.add(int(amount), attributes)


artifacts_size_counter = ArtifactsSizeCounter.build()
