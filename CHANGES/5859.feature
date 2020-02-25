Added a ``pulpcore-manager`` script that is ``django-admin`` only configured with
``DJANGO_SETTINGS_MODULE="pulpcore.app.settings"``. This can be used for things like applying
database migrations or collecting static media.
