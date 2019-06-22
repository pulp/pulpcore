Each Content App now heartbeats periodically, and Content Apps with recent heartbeats are shown in
the Status API ``/pulp/api/v3/status/`` as a list called ``online_content_apps``. A new setting is
introduced named ``CONTENT_APP_TTL`` which specifies the maximum time (in seconds) a Content App can
not heartbeat and be considered online.
