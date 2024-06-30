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
  # Unified Docs Build
  pulp-docs build
  # Legacy Docs Build
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

# Generate bindings
###################

echo "::group::Generate bindings"

touch bindings_requirements.txt
pushd ../pulp-openapi-generator
  # Use app_label to generate api.json and package to produce the proper package name.

  # Workaround: Domains are not supported by the published bindings.
  # Sadly: Different pulpcore-versions aren't either...
  # So we exclude the prebuilt ones only for domains disabled.
  if [ "$(jq -r '.domain_enabled' <<<"${REPORTED_STATUS}")" = "true" ] || [ "$(jq -r '.online_workers[0].pulp_href|startswith("/pulp/api/v3/")' <<< "${REPORTED_STATUS}")" = "false" ]
  then
    BUILT_CLIENTS=""
  else
    BUILT_CLIENTS=" core file certguard "
  fi

  for ITEM in $(jq -r '.versions[] | tojson' <<<"${REPORTED_STATUS}")
  do
    COMPONENT="$(jq -r '.component' <<<"${ITEM}")"
    VERSION="$(jq -r '.version' <<<"${ITEM}" | python3 -c "from packaging.version import Version; print(Version(input()))")"
    # On older status endpoints, the module was not provided, but the package should be accurate
    # there, because we did not merge plugins into pulpcore back then.
    MODULE="$(jq -r '.module // (.package|gsub("-"; "_"))' <<<"${ITEM}")"
    PACKAGE="${MODULE%%.*}"
    cmd_prefix pulpcore-manager openapi --bindings --component "${COMPONENT}" > "${COMPONENT}-api.json"
    if [[ ! " ${BUILT_CLIENTS} " =~ "${COMPONENT}" ]]
    then
      rm -rf "./${PACKAGE}-client"
      ./gen-client.sh "${COMPONENT}-api.json" "${COMPONENT}" python "${PACKAGE}"
      pushd "${PACKAGE}-client"
        python setup.py sdist bdist_wheel --python-tag py3
      popd
    else
      if [ ! -f "${PACKAGE}-client/dist/${PACKAGE}_client-${VERSION}-py3-none-any.whl" ]
      then
        ls -lR "${PACKAGE}-client/"
        echo "Error: Client bindings for ${COMPONENT} not found."
        echo "File ${PACKAGE}-client/dist/${PACKAGE}_client-${VERSION}-py3-none-any.whl missing."
        exit 1
      fi
    fi
    echo "/root/pulp-openapi-generator/${PACKAGE}-client/dist/${PACKAGE}_client-${VERSION}-py3-none-any.whl" >> "../pulpcore/bindings_requirements.txt"
  done
popd

echo "::endgroup::"

echo "::group::Debug bindings diffs"

# Bindings diff for core
jq '(.paths[][].parameters|select(.)) |= sort_by(.name)' < "core-api.json" > "build-api.json"
jq '(.paths[][].parameters|select(.)) |= sort_by(.name)' < "../pulp-openapi-generator/core-api.json" > "test-api.json"
jsondiff --indent 2 build-api.json test-api.json || true
# Bindings diff for file
jq '(.paths[][].parameters|select(.)) |= sort_by(.name)' < "file-api.json" > "build-api.json"
jq '(.paths[][].parameters|select(.)) |= sort_by(.name)' < "../pulp-openapi-generator/file-api.json" > "test-api.json"
jsondiff --indent 2 build-api.json test-api.json || true
# Bindings diff for certguard
jq '(.paths[][].parameters|select(.)) |= sort_by(.name)' < "certguard-api.json" > "build-api.json"
jq '(.paths[][].parameters|select(.)) |= sort_by(.name)' < "../pulp-openapi-generator/certguard-api.json" > "test-api.json"
jsondiff --indent 2 build-api.json test-api.json || true
echo "::endgroup::"

# Install test requirements
###########################

# Add a safeguard to make sure the proper versions of the clients are installed.
echo "$REPORTED_STATUS" | jq -r '.versions[]|select(.package)|(.package|sub("_"; "-")) + "-client==" + .version' > bindings_constraints.txt
cmd_stdin_prefix bash -c "cat > /tmp/unittest_requirements.txt" < unittest_requirements.txt
cmd_stdin_prefix bash -c "cat > /tmp/functest_requirements.txt" < functest_requirements.txt
cmd_stdin_prefix bash -c "cat > /tmp/bindings_requirements.txt" < bindings_requirements.txt
cmd_stdin_prefix bash -c "cat > /tmp/bindings_constraints.txt" < bindings_constraints.txt
cmd_prefix pip3 install -r /tmp/unittest_requirements.txt -r /tmp/functest_requirements.txt -r /tmp/bindings_requirements.txt -c /tmp/bindings_constraints.txt

CERTIFI=$(cmd_prefix python3 -c 'import certifi; print(certifi.where())')
cmd_prefix bash -c "cat /etc/pulp/certs/pulp_webserver.crt >> '$CERTIFI'"

# check for any uncommitted migrations
echo "Checking for uncommitted migrations..."
cmd_user_prefix bash -c "django-admin makemigrations core --check --dry-run"
cmd_user_prefix bash -c "django-admin makemigrations file --check --dry-run"
cmd_user_prefix bash -c "django-admin makemigrations certguard --check --dry-run"

# Run unit tests.
cmd_user_prefix bash -c "PULP_DATABASES__default__USER=postgres pytest -v -r sx --color=yes --suppress-no-test-exit-code -p no:pulpcore --pyargs pulpcore.tests.unit"
cmd_user_prefix bash -c "PULP_DATABASES__default__USER=postgres pytest -v -r sx --color=yes --suppress-no-test-exit-code -p no:pulpcore --pyargs pulp_file.tests.unit"
cmd_user_prefix bash -c "PULP_DATABASES__default__USER=postgres pytest -v -r sx --color=yes --suppress-no-test-exit-code -p no:pulpcore --pyargs pulp_certguard.tests.unit"
# Run functional tests
if [[ "$TEST" == "performance" ]]; then
  if [[ -z ${PERFORMANCE_TEST+x} ]]; then
    cmd_user_prefix bash -c "pytest -vv -r sx --color=yes --suppress-no-test-exit-code --capture=no --durations=0 --pyargs pulpcore.tests.performance"
    cmd_user_prefix bash -c "pytest -vv -r sx --color=yes --suppress-no-test-exit-code --capture=no --durations=0 --pyargs pulp_file.tests.performance"
    cmd_user_prefix bash -c "pytest -vv -r sx --color=yes --suppress-no-test-exit-code --capture=no --durations=0 --pyargs pulp_certguard.tests.performance"
  else
    cmd_user_prefix bash -c "pytest -vv -r sx --color=yes --suppress-no-test-exit-code --capture=no --durations=0 --pyargs pulpcore.tests.performance.test_${PERFORMANCE_TEST}"
    cmd_user_prefix bash -c "pytest -vv -r sx --color=yes --suppress-no-test-exit-code --capture=no --durations=0 --pyargs pulp_file.tests.performance.test_${PERFORMANCE_TEST}"
    cmd_user_prefix bash -c "pytest -vv -r sx --color=yes --suppress-no-test-exit-code --capture=no --durations=0 --pyargs pulp_certguard.tests.performance.test_${PERFORMANCE_TEST}"
  fi
  exit
fi

if [ -f "$FUNC_TEST_SCRIPT" ]; then
  source "$FUNC_TEST_SCRIPT"
else
  if [[ "$GITHUB_WORKFLOW" =~ "Nightly" ]]
  then
    cmd_user_prefix bash -c "pytest -v -r sx --color=yes --suppress-no-test-exit-code --pyargs pulpcore.tests.functional -m parallel -n 8 --nightly"
    cmd_user_prefix bash -c "pytest -v -r sx --color=yes --suppress-no-test-exit-code --pyargs pulpcore.tests.functional -m 'not parallel' --nightly"
    cmd_user_prefix bash -c "pytest -v -r sx --color=yes --suppress-no-test-exit-code --pyargs pulp_file.tests.functional -m parallel -n 8 --nightly"
    cmd_user_prefix bash -c "pytest -v -r sx --color=yes --suppress-no-test-exit-code --pyargs pulp_file.tests.functional -m 'not parallel' --nightly"
    cmd_user_prefix bash -c "pytest -v -r sx --color=yes --suppress-no-test-exit-code --pyargs pulp_certguard.tests.functional -m parallel -n 8 --nightly"
    cmd_user_prefix bash -c "pytest -v -r sx --color=yes --suppress-no-test-exit-code --pyargs pulp_certguard.tests.functional -m 'not parallel' --nightly"
  else
    cmd_user_prefix bash -c "pytest -v -r sx --color=yes --suppress-no-test-exit-code --pyargs pulpcore.tests.functional -m parallel -n 8"
    cmd_user_prefix bash -c "pytest -v -r sx --color=yes --suppress-no-test-exit-code --pyargs pulpcore.tests.functional -m 'not parallel'"
    cmd_user_prefix bash -c "pytest -v -r sx --color=yes --suppress-no-test-exit-code --pyargs pulp_file.tests.functional -m parallel -n 8"
    cmd_user_prefix bash -c "pytest -v -r sx --color=yes --suppress-no-test-exit-code --pyargs pulp_file.tests.functional -m 'not parallel'"
    cmd_user_prefix bash -c "pytest -v -r sx --color=yes --suppress-no-test-exit-code --pyargs pulp_certguard.tests.functional -m parallel -n 8"
    cmd_user_prefix bash -c "pytest -v -r sx --color=yes --suppress-no-test-exit-code --pyargs pulp_certguard.tests.functional -m 'not parallel'"
  fi
fi
export PULP_FIXTURES_URL="http://pulp-fixtures:8080"
pushd ../pulp-cli
pip install -r test_requirements.txt
pytest -v -m "pulpcore or pulp_file or pulp_certguard"
popd

if [ -f "$POST_SCRIPT" ]; then
  source "$POST_SCRIPT"
fi
