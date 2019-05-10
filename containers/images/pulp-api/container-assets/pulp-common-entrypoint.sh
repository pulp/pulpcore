#!/bin/bash

export DJANGO_SETTINGS_MODULE=pulpcore.app.settings

exec "$@"
