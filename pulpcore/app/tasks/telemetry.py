from django.db.models import Sum

from pulpcore.app.models import Artifact

from opentelemetry.sdk.metrics import MeterProvider

from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource


def otel_metrics():

    # This configuration is needed since the worker thread is not using the opentelemetry
    # instrumentation agent to run the task code.

    exporter = OTLPMetricExporter()

    resource = Resource(attributes={"service.name": "pulp-worker"})

    metric_reader = PeriodicExportingMetricReader(exporter)
    provider = MeterProvider(metric_readers=[metric_reader], resource=resource)

    meter = provider.get_meter(__name__)
    space_usage_gauge = meter.create_gauge(
        name="space_usage",
        description="The total space usage per domain.",
        unit="bytes",
    )

    space_usage_per_domain = Artifact.objects.values("pulp_domain__name").annotate(
        total_size=Sum("size", default=0)
    )

    # We're using the same gauge with different attributes for each domain space usage
    for domain in space_usage_per_domain:
        space_usage_gauge.set(domain["total_size"], {"domain_name": domain["pulp_domain__name"]})

    metric_reader.collect()
