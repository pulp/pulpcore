Workers no longer require names, and auto-name as {pid}@{fqdn}. This allows easy finding of
processes from the Status API. Custom names still work by specifying the ``-n`` option when starting
a worker. Any worker name starting with ``resource-manager`` is a resource-manager, otherwise it's
assumed to be a task worker.
