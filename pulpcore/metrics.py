from opentelemetry import metrics

from pulpcore.app.util import MetricsEmitter, get_domain, get_worker_name


class ArtifactsSizeCounter(MetricsEmitter):
    def __init__(self):
        self.meter = metrics.get_meter("artifacts.size.meter")
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
