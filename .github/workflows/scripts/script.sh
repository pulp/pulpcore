#!/usr/bin/env bash
# coding=utf-8

# WARNING: DO NOT EDIT!
#
# This file was generated by plugin_template, and is managed by it. Please use
# './plugin-template --github pulpcore' to update this file.
#
# For more info visit https://github.com/pulp/plugin_template

# make sure this script runs at the repo root
cd "$(dirname "$(realpath -e "$0")")"/../../..
REPO_ROOT="$PWD"

set -mveuo pipefail

source .github/workflows/scripts/utils.sh

export POST_SCRIPT=$PWD/.github/workflows/scripts/post_script.sh
export POST_DOCS_TEST=$PWD/.github/workflows/scripts/post_docs_test.sh
export FUNC_TEST_SCRIPT=$PWD/.github/workflows/scripts/func_test_script.sh

# Needed for both starting the service and building the docs.
# Gets set in .github/settings.yml, but doesn't seem to inherited by
# this script.
export DJANGO_SETTINGS_MODULE=pulpcore.app.settings
export PULP_SETTINGS=$PWD/.ci/ansible/settings/settings.py

export PULP_URL="https://pulp"

if [[ "$TEST" = "docs" ]]; then
  cd docs
  make PULP_URL="$PULP_URL" diagrams html
  tar -cvf docs.tar ./_build
  cd ..

  echo "Validating OpenAPI schema..."
  cat $PWD/.ci/scripts/schema.py | cmd_stdin_prefix bash -c "cat > /tmp/schema.py"
  cmd_prefix bash -c "python3 /tmp/schema.py"
  cmd_prefix bash -c "pulpcore-manager spectacular --file pulp_schema.yml --validate"

  if [ -f $POST_DOCS_TEST ]; then
    source $POST_DOCS_TEST
  fi
  exit
fi

if [[ "${RELEASE_WORKFLOW:-false}" == "true" ]]; then
  REPORTED_VERSION=$(http $PULP_URL/pulp/api/v3/status/ | jq --arg plugin core --arg legacy_plugin pulpcore -r '.versions[] | select(.component == $plugin or .component == $legacy_plugin) | .version')
  response=$(curl --write-out %{http_code} --silent --output /dev/null https://pypi.org/project/pulpcore/$REPORTED_VERSION/)
  if [ "$response" == "200" ];
  then
    echo "pulpcore $REPORTED_VERSION has already been released. Skipping running tests."
    exit
  fi
fi

if [[ "$TEST" == "plugin-from-pypi" ]]; then
  COMPONENT_VERSION=$(http https://pypi.org/pypi/pulpcore/json | jq -r '.info.version')
  git checkout ${COMPONENT_VERSION} -- pulpcore/tests/
fi

cd ../pulp-openapi-generator
./generate.sh pulp_file python
pip install ./pulp_file-client
rm -rf ./pulp_file-client
if [[ "$TEST" = 'bindings' ]]; then
  ./generate.sh pulp_file ruby 0
  cd pulp_file-client
  gem build pulp_file_client.gemspec
  gem install --both ./pulp_file_client-0.gem
  cd ..
fi
./generate.sh pulp_certguard python
pip install ./pulp_certguard-client
rm -rf ./pulp_certguard-client
if [[ "$TEST" = 'bindings' ]]; then
  ./generate.sh pulp-certguard ruby 0
  cd pulp-certguard-client
  gem build pulp-certguard_client.gemspec
  gem install --both ./pulp-certguard_client-0.gem
  cd ..
fi
cd $REPO_ROOT

if [[ "$TEST" = 'bindings' ]]; then
  python $REPO_ROOT/.ci/assets/bindings/test_bindings.py
fi

if [[ "$TEST" = 'bindings' ]]; then
  if [ ! -f $REPO_ROOT/.ci/assets/bindings/test_bindings.rb ]; then
    exit
  else
    ruby $REPO_ROOT/.ci/assets/bindings/test_bindings.rb
    exit
  fi
fi

cat unittest_requirements.txt | cmd_stdin_prefix bash -c "cat > /tmp/unittest_requirements.txt"
cmd_prefix pip3 install -r /tmp/unittest_requirements.txt

# check for any uncommitted migrations
echo "Checking for uncommitted migrations..."
cmd_prefix bash -c "django-admin makemigrations --check --dry-run"

# Run unit tests.
cmd_prefix bash -c "PULP_DATABASES__default__USER=postgres django-admin test --noinput /usr/local/lib/python3.6/site-packages/pulpcore/tests/unit/"

# Run functional tests
export PYTHONPATH=$REPO_ROOT${PYTHONPATH:+:${PYTHONPATH}}


if [[ "$TEST" == "upgrade" ]]; then
  # Handle app label change:
  sed -i "/require_pulp_plugins(/d" pulpcore/tests/functional/utils.py

  # Running pre upgrade tests:
  pytest -v -r sx --color=yes --pyargs -capture=no pulpcore.tests.upgrade.pre

  # Checking out ci_upgrade_test branch and upgrading plugins
  cmd_prefix bash -c "cd pulp-certguard; git checkout -f ci_upgrade_test; pip install ."
  cmd_prefix bash -c "cd pulp_file; git checkout -f ci_upgrade_test; pip install ."
  cmd_prefix bash -c "cd pulpcore; git checkout -f ci_upgrade_test; pip install ."

  # Migrating
  cmd_prefix bash -c "django-admin migrate --no-input"

  # Restarting single container services
  cmd_prefix bash -c "s6-svc -r /var/run/s6/services/pulpcore-api"
  cmd_prefix bash -c "s6-svc -r /var/run/s6/services/pulpcore-content"
  cmd_prefix bash -c "s6-svc -d /var/run/s6/services/pulpcore-resource-manager"
  cmd_prefix bash -c "s6-svc -d /var/run/s6/services/pulpcore-worker@1"
  cmd_prefix bash -c "s6-svc -d /var/run/s6/services/pulpcore-worker@2"
  cmd_prefix bash -c "s6-svc -u /var/run/s6/services/new-pulpcore-resource-manager"
  cmd_prefix bash -c "s6-svc -u /var/run/s6/services/new-pulpcore-worker@1"
  cmd_prefix bash -c "s6-svc -u /var/run/s6/services/new-pulpcore-worker@2"

  echo "Restarting in 60 seconds"
  sleep 60

  # CLI commands to display plugin versions and content data
  pulp status
  pulp content list
  CONTENT_LENGTH=$(pulp content list | jq length)
  if [[ "$CONTENT_LENGTH" == "0" ]]; then
    echo "Empty content list"
    exit 1
  fi

  # Rebuilding bindings
  cd ../pulp-openapi-generator
  ./generate.sh pulpcore python
  pip install ./pulpcore-client
  ./generate.sh pulp_file python
  pip install ./pulp_file-client
  ./generate.sh pulp_certguard python
  pip install ./pulp_certguard-client
  cd $REPO_ROOT

  # Running post upgrade tests
  git checkout ci_upgrade_test -- pulpcore/tests/
  pytest -v -r sx --color=yes --pyargs -capture=no pulpcore.tests.upgrade.post
  exit
fi


if [[ "$TEST" == "performance" ]]; then
  if [[ -z ${PERFORMANCE_TEST+x} ]]; then
    pytest -vv -r sx --color=yes --pyargs --capture=no --durations=0 pulpcore.tests.performance
  else
    pytest -vv -r sx --color=yes --pyargs --capture=no --durations=0 pulpcore.tests.performance.test_$PERFORMANCE_TEST
  fi
  exit
fi

if [ -f $FUNC_TEST_SCRIPT ]; then
  source $FUNC_TEST_SCRIPT
else
    pytest -v -r sx --color=yes --pyargs pulpcore.tests.functional
fi
export PULP_FIXTURES_URL="http://pulp-fixtures:8080"
pushd ../pulp-cli
pytest -v -m pulpcore
popd

if [ -f $POST_SCRIPT ]; then
  source $POST_SCRIPT
fi
