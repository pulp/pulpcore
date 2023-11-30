#!/usr/bin/env bash
# coding=utf-8

# WARNING: DO NOT EDIT!
#
# This file was generated by plugin_template, and is managed by it. Please use
# './plugin-template --github pulpcore' to update this file.
#
# For more info visit https://github.com/pulp/plugin_template

set -mveuo pipefail

# make sure this script runs at the repo root
cd "$(dirname "$(realpath -e "$0")")"/../../..

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
  if [[ "$GITHUB_WORKFLOW" == "Core CI" ]]; then
    towncrier build --yes --version 4.0.0.ci
  fi
  cd docs
  make PULP_URL="$PULP_URL" diagrams html
  tar -cvf docs.tar ./_build
  cd ..

  if [ -f "$POST_DOCS_TEST" ]; then
    source "$POST_DOCS_TEST"
  fi
  exit
fi

REPORTED_STATUS="$(pulp status)"

echo "machine pulp
login admin
password password
" | cmd_user_stdin_prefix bash -c "cat >> ~pulp/.netrc"
# Some commands like ansible-galaxy specifically require 600
cmd_prefix bash -c "chmod 600 ~pulp/.netrc"

# Infer the client name from the package name by replacing "-" with "_".
# Use the component to infer the package name on older versions of pulpcore.

if [ "$(echo "$REPORTED_STATUS" | jq -r '.domain_enabled')" = "true" ]
then
  # Workaround: Domains are not supported by the published bindings.
  # Generate new bindings for all packages.
  pushd ../pulp-openapi-generator
  for item in $(echo "$REPORTED_STATUS" | jq -r '.versions[]|(.package // ("pulp_" + .component)|sub("pulp_core"; "pulpcore"))|sub("-"; "_")')
  do
    ./generate.sh "${item}" python
    cmd_prefix pip3 install "/root/pulp-openapi-generator/${item}-client"
    sudo rm -rf "./${item}-client"
  done
  popd
else
  # Sadly: Different pulpcore-versions aren't either...
  pushd ../pulp-openapi-generator
  for item in $(echo "$REPORTED_STATUS" | jq -r '.versions[]|select(.component!="core")|(.package // ("pulp_" + .component)|sub("pulp_core"; "pulpcore"))|sub("-"; "_")')
  do
    ./generate.sh "${item}" python
    cmd_prefix pip3 install "/root/pulp-openapi-generator/${item}-client"
    sudo rm -rf "./${item}-client"
  done
  popd
fi

# At this point, this is a safeguard only, so let's not make too much fuzz about the old status format.
echo "$REPORTED_STATUS" | jq -r '.versions[]|select(.package)|(.package|sub("_"; "-")) + "-client==" + .version' > bindings_requirements.txt
cmd_stdin_prefix bash -c "cat > /tmp/unittest_requirements.txt" < unittest_requirements.txt
cmd_stdin_prefix bash -c "cat > /tmp/functest_requirements.txt" < functest_requirements.txt
cmd_stdin_prefix bash -c "cat > /tmp/bindings_requirements.txt" < bindings_requirements.txt
cmd_prefix pip3 install -r /tmp/unittest_requirements.txt -r /tmp/functest_requirements.txt -r /tmp/bindings_requirements.txt

CERTIFI=$(cmd_prefix python3 -c 'import certifi; print(certifi.where())')
cmd_prefix bash -c "cat /etc/pulp/certs/pulp_webserver.crt >> '$CERTIFI'"

# check for any uncommitted migrations
echo "Checking for uncommitted migrations..."
cmd_user_prefix bash -c "django-admin makemigrations core --check --dry-run"

# Run unit tests.
cmd_user_prefix bash -c "PULP_DATABASES__default__USER=postgres pytest -v -r sx --color=yes -p no:pulpcore --pyargs pulpcore.tests.unit"

# Run functional tests
if [[ "$TEST" == "performance" ]]; then
  if [[ -z ${PERFORMANCE_TEST+x} ]]; then
    cmd_user_prefix bash -c "pytest -vv -r sx --color=yes --pyargs --capture=no --durations=0 pulpcore.tests.performance"
  else
    cmd_user_prefix bash -c "pytest -vv -r sx --color=yes --pyargs --capture=no --durations=0 pulpcore.tests.performance.test_${PERFORMANCE_TEST}"
  fi
  exit
fi

if [ -f "$FUNC_TEST_SCRIPT" ]; then
  source "$FUNC_TEST_SCRIPT"
else
    if [[ "$GITHUB_WORKFLOW" == "Core Nightly CI/CD" ]]
    then
        cmd_user_prefix bash -c "pytest -v -r sx --color=yes --suppress-no-test-exit-code --pyargs pulpcore.tests.functional -m parallel -n 8 --nightly"
        cmd_user_prefix bash -c "pytest -v -r sx --color=yes --pyargs pulpcore.tests.functional -m 'not parallel' --nightly"

    else
        cmd_user_prefix bash -c "pytest -v -r sx --color=yes --suppress-no-test-exit-code --pyargs pulpcore.tests.functional -m parallel -n 8"
        cmd_user_prefix bash -c "pytest -v -r sx --color=yes --pyargs pulpcore.tests.functional -m 'not parallel'"
    fi
fi
export PULP_FIXTURES_URL="http://pulp-fixtures:8080"
pushd ../pulp-cli
pip install -r test_requirements.txt
pytest -v -m pulpcore
popd

if [ -f "$POST_SCRIPT" ]; then
  source "$POST_SCRIPT"
fi
