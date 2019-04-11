#!/usr/bin/env bash
# coding=utf-8

set -mveuo pipefail

# Needed for both starting the service and building the docs.
# Gets set in .travis/settings.yml, but doesn't seem to inherited by
# this script.
export DJANGO_SETTINGS_MODULE=pulpcore.app.settings

wait_for_pulp() {
  TIMEOUT=${1:-5}
  while [ "$TIMEOUT" -gt 0 ]
  do
    echo -n .
    sleep 1
    TIMEOUT=$(($TIMEOUT - 1))
    if [ $(http :24817/pulp/api/v3/status/ | jq '.database_connection.connected and .redis_connection.connected') = 'true' ]
    then
      echo
      return
    fi
  done
  echo
  return 1
}

if [ "$TEST" = 'docs' ]; then
  django-admin runserver 24817 >> ~/django_runserver.log 2>&1 &
  sleep 5
  cd docs
  make html
  exit
fi

# check the commit message
./.travis/check_commit.sh

# Lint code.
flake8 --config flake8.cfg

# Run unit tests.
coverage run manage.py test ./pulpcore/tests/unit/

# Run functional tests, and upload coverage report to codecov.
show_logs_and_return_non_zero() {
    readonly local rc="$?"
    cat ~/django_runserver.log
    cat ~/content_app.log
    cat ~/resource_manager.log
    cat ~/reserved_worker-1.log
    return "${rc}"
}

# Stop services started by ansible roles
sudo systemctl stop pulp-worker* pulp-resource-manager pulp-content-app pulp-api

# Start services with logs and coverage
export PULP_CONTENT_HOST=localhost:24816
rq worker -n 'resource-manager@%h' -w 'pulpcore.tasking.worker.PulpWorker' -c 'pulpcore.rqconfig' >> ~/resource_manager.log 2>&1 &
rq worker -n 'reserved-resource-worker-1@%h' -w 'pulpcore.tasking.worker.PulpWorker' -c 'pulpcore.rqconfig' >> ~/reserved_worker-1.log 2>&1 &
gunicorn pulpcore.tests.functional.content_with_coverage:server --bind 'localhost:24816' --worker-class 'aiohttp.GunicornWebWorker' -w 2 >> ~/content_app.log 2>&1 &
coverage run $(which django-admin) runserver 24817 --noreload >> ~/django_runserver.log 2>&1 &
wait_for_pulp 20

# Run functional tests
pytest -v -r sx --color=yes --pyargs pulpcore.tests.functional || show_logs_and_return_non_zero
pytest -v -r sx --color=yes --pyargs pulp_file.tests.functional || show_logs_and_return_non_zero
pytest -v -r sx --color=yes --pyargs pulp_certguard.tests.functional || show_logs_and_return_non_zero

# Stop services to write coverage
kill -SIGINT %?runserver
kill -SIGINT %?content_with_coverage
kill -SIGINT %?reserved-resource-worker
kill -SIGINT %?resource-manager
wait || true

coverage combine
codecov
