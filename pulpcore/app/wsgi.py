"""
WSGI config for pulp project.

It exposes the WSGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/3.2/howto/deployment/wsgi/
"""

from django.core.wsgi import get_wsgi_application
from opentelemetry.instrumentation.wsgi import OpenTelemetryMiddleware
from opentelemetry.exporter.otlp.proto.http.metric_exporter import (
    OTLPMetricExporter,
)
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader

from pulpcore.app.entrypoint import using_pulp_api_worker
from pulpcore.app.util import get_worker_name
from opentelemetry.sdk.resources import Resource

if not using_pulp_api_worker.get(False):
    raise RuntimeError("This app must be executed using pulpcore-api entrypoint.")


class WorkerNameMetricsExporter(OTLPMetricExporter):
    def export(self, metrics_data, timeout_millis=10_000, **kwargs):
        for resource_metric in metrics_data.resource_metrics:
            for scope_metric in resource_metric.scope_metrics:
                for metric in scope_metric.metrics:
                    if metric.data.data_points:
                        point = metric.data.data_points[0]
                        point.attributes["worker.name"] = get_worker_name()

        return super().export(metrics_data, timeout_millis, **kwargs)


exporter = WorkerNameMetricsExporter()
reader = PeriodicExportingMetricReader(exporter)
resource = Resource(attributes={"service.name": "pulp-api"})
provider = MeterProvider(metric_readers=[reader], resource=resource)

application = get_wsgi_application()
application = OpenTelemetryMiddleware(application, meter_provider=provider)

# Disabling Storage metrics until we find a solution to resource usage.
# https://github.com/pulp/pulpcore/issues/5468
# from pulpcore.app.util import init_domain_metrics_exporter  # noqa: E402

# init_domain_metrics_exporter()
