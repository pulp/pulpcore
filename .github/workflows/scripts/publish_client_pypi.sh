#!/bin/bash

# WARNING: DO NOT EDIT!
#
# This file was generated by plugin_template, and is managed by it. Please use
# './plugin-template --github pulpcore' to update this file.
#
# For more info visit https://github.com/pulp/plugin_template

set -euv

# make sure this script runs at the repo root
cd "$(dirname "$(realpath -e "$0")")/../../.."

VERSION="$1"

if [[ -z "${VERSION}" ]]
then
  echo "No version specified."
  exit 1
fi

twine upload -u __token__ -p "${PYPI_API_TOKEN}" \
"dist/pulpcore_client-${VERSION}-py3-none-any.whl" \
"dist/pulpcore-client-${VERSION}.tar.gz" \
"dist/pulp_file_client-${VERSION}-py3-none-any.whl" \
"dist/pulp_file-client-${VERSION}.tar.gz" \
"dist/pulp_certguard_client-${VERSION}-py3-none-any.whl" \
"dist/pulp_certguard-client-${VERSION}.tar.gz" \
;
