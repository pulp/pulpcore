#!/usr/bin/env bash

# WARNING: DO NOT EDIT!
#
# This file was generated by plugin_template, and is managed by it. Please use
# './plugin-template --github pulpcore' to update this file.
#
# For more info visit https://github.com/pulp/plugin_template

# make sure this script runs at the repo root
cd "$(dirname "$(realpath -e "$0")")"/../../..
REPO_ROOT="$PWD"

set -euv

source .github/workflows/scripts/utils.sh

if [[ "$TEST" = "docs" || "$TEST" = "publish" ]]; then
  pip install psycopg2-binary
  pip install -r doc_requirements.txt
fi

pip install -r functest_requirements.txt

cd .ci/ansible/

TAG=ci_build

if [ -e $REPO_ROOT/../pulp_file ]; then
  PULP_FILE=./pulp_file
else
  PULP_FILE=git+https://github.com/pulp/pulp_file.git@master
fi

if [ -e $REPO_ROOT/../pulp-certguard ]; then
  PULP_CERTGUARD=./pulp-certguard
else
  PULP_CERTGUARD=git+https://github.com/pulp/pulp-certguard.git@master
fi
if [[ "${RELEASE_WORKFLOW:-false}" == "true" ]]; then
  PLUGIN_NAME=./pulpcore/dist/pulpcore-$PLUGIN_VERSION-py3-none-any.whl
else
  PLUGIN_NAME=./pulpcore
fi
cat >> vars/main.yaml << VARSYAML
image:
  name: pulp
  tag: "${TAG}"
plugins:
  - name: pulpcore
    source: "${PLUGIN_NAME}"
  - name: pulp_file
    source: $PULP_FILE
  - name: pulp-certguard
    source: $PULP_CERTGUARD
services:
  - name: pulp
    image: "pulp:${TAG}"
    volumes:
      - ./settings:/etc/pulp
VARSYAML

cat >> vars/main.yaml << VARSYAML
pulp_settings: {"allowed_export_paths": ["/tmp"], "allowed_import_paths": ["/tmp"]}
pulp_scheme: https
pulp_container_tag: https
VARSYAML

if [[ "$TEST" == "pulp" || "$TEST" == "performance" || "$TEST" == "upgrade" || "$TEST" == "s3" || "$TEST" == "plugin-from-pypi" ]]; then
  sed -i -e '/^services:/a \
  - name: pulp-fixtures\
    image: docker.io/pulp/pulp-fixtures:latest\
    env: {BASE_URL: "http://pulp-fixtures:8080"}' vars/main.yaml
fi

if [ "$TEST" = "s3" ]; then
  export MINIO_ACCESS_KEY=AKIAIT2Z5TDYPX3ARJBA
  export MINIO_SECRET_KEY=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
  sed -i -e '/^services:/a \
  - name: minio\
    image: minio/minio\
    env:\
      MINIO_ACCESS_KEY: "'$MINIO_ACCESS_KEY'"\
      MINIO_SECRET_KEY: "'$MINIO_SECRET_KEY'"\
    command: "server /data"' vars/main.yaml
  sed -i -e '$a s3_test: true\
minio_access_key: "'$MINIO_ACCESS_KEY'"\
minio_secret_key: "'$MINIO_SECRET_KEY'"' vars/main.yaml
fi

ansible-playbook build_container.yaml
ansible-playbook start_container.yaml
echo ::group::SSL
# Copy pulp CA
sudo docker cp pulp:/etc/pulp/certs/pulp_webserver.crt /usr/local/share/ca-certificates/pulp_webserver.crt

# Hack: adding pulp CA to certifi.where()
CERTIFI=$(python -c 'import certifi; print(certifi.where())')
cat /usr/local/share/ca-certificates/pulp_webserver.crt | sudo tee -a $CERTIFI

# Hack: adding pulp CA to default CA file
CERT=$(python -c 'import ssl; print(ssl.get_default_verify_paths().openssl_cafile)')
cat $CERTIFI | sudo tee -a $CERT

# Updating certs
sudo update-ca-certificates
echo ::endgroup::

echo ::group::PIP_LIST
cmd_prefix bash -c "pip3 list && pip3 install pipdeptree && pipdeptree"
echo ::endgroup::
