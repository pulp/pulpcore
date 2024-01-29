Started emitting metrics that report disk usage within a domain. The metrics are sent to the
collector every 60 seconds. The interval can be adjusted with the ``OTEL_METRIC_EXPORT_INTERVAL``
environemnt variable.
