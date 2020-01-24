Add optional prometheus metrics support

This enables pulpcore to export pulp metrics to
be scraped by prometheus if the django module 'django_prometheus'
(https://github.com/korfuri/django-prometheus) is installed.

If 'django_prometheus' is available, the '/metrics'
url will contain metrics that can be collected
by https://prometheus.io/
