"""
WSGI config for pulp project.

It exposes the WSGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/3.2/howto/deployment/wsgi/
"""

from django.core.wsgi import get_wsgi_application
from opentelemetry.instrumentation.wsgi import OpenTelemetryMiddleware

from pulpcore.app.entrypoint import using_pulp_api_worker

if not using_pulp_api_worker.get(False):
    raise RuntimeError("This app must be executed using pulpcore-api entrypoint.")

application = get_wsgi_application()
application = OpenTelemetryMiddleware(application)

from pulpcore.app.util import init_domain_metrics_exporter  # noqa: E402

init_domain_metrics_exporter()
