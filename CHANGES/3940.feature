Added graceful shutdown to pulpcore-worker without killing the current task on receiving
``SIGHUP`` or ``SIGTERM``.
