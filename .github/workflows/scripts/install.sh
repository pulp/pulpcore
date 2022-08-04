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

export PULP_API_ROOT="/pulp/"

cd .ci/ansible/

TAG=ci_build
if [ -e $REPO_ROOT/../pulp_file ]; then
  PULP_FILE=./pulp_file
else
  PULP_FILE=git+https://github.com/pulp/pulp_file.git@1.10
fi
if [ -e $REPO_ROOT/../pulp-certguard ]; then
  PULP_CERTGUARD=./pulp-certguard
else
  PULP_CERTGUARD=git+https://github.com/pulp/pulp-certguard.git@1.5
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
  - name: pulp-smash
    source: ./pulp-smash
VARSYAML

cat >> vars/main.yaml << VARSYAML
services:
  - name: pulp
    image: "pulp:${TAG}"
    volumes:
      - ./settings:/etc/pulp
      - ./ssh:/keys/
      - ~/.config:/root/.config
      - ../../../pulp-openapi-generator:/root/pulp-openapi-generator
VARSYAML

cat >> vars/main.yaml << VARSYAML
pulp_settings: {"allowed_export_paths": ["/tmp"], "allowed_import_paths": ["/tmp"], "orphan_protection_time": 0}
pulp_scheme: https

pulp_container_tag: https

VARSYAML

SCENARIOS=("pulp" "performance" "azure" "s3" "stream" "plugin-from-pypi" "generate-bindings")
if [[ " ${SCENARIOS[*]} " =~ " ${TEST} " ]]; then
  sed -i -e '/^services:/a \
  - name: pulp-fixtures\
    image: docker.io/pulp/pulp-fixtures:latest\
    env: {BASE_URL: "http://pulp-fixtures:8080"}' vars/main.yaml
fi
if [ "$TEST" == 'stream' ]; then
  sed -i -e '/^services:/a \
  - name: ci-sftp\
    image: atmoz/sftp\
    volumes:\
      - ./ssh/id_ed25519.pub:/home/foo/.ssh/keys/id_ed25519.pub\
    command: "foo::::storage"' vars/main.yaml
  sed -i -e '$a stream_test: true' vars/main.yaml
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
  export PULP_API_ROOT="/rerouted/djnd/"
fi

if [ "$TEST" = "azure" ]; then
  mkdir -p azurite
  cd azurite
  openssl req -newkey rsa:2048 -x509 -nodes -keyout azkey.pem -new -out azcert.pem -sha256 -days 365 -addext "subjectAltName=DNS:ci-azurite" -subj "/C=CO/ST=ST/L=LO/O=OR/OU=OU/CN=CN"
  sudo cp azcert.pem /usr/local/share/ca-certificates/azcert.crt
  sudo dpkg-reconfigure ca-certificates
  cd ..
  sed -i -e '/^services:/a \
  - name: ci-azurite\
    image: mcr.microsoft.com/azure-storage/azurite\
    volumes:\
      - ./azurite:/etc/pulp\
    command: "azurite-blob --blobHost 0.0.0.0 --cert /etc/pulp/azcert.pem --key /etc/pulp/azkey.pem"' vars/main.yaml
  sed -i -e '$a azure_test: true' vars/main.yaml
fi

echo "PULP_API_ROOT=${PULP_API_ROOT}" >> "$GITHUB_ENV"

if [ "${PULP_API_ROOT:-}" ]; then
  sed -i -e '$a api_root: "'"$PULP_API_ROOT"'"' vars/main.yaml
fi

ansible-playbook build_container.yaml
ansible-playbook start_container.yaml

if [[ "$TEST" = "docs" || "$TEST" = "publish" ]]; then
  pip install psycopg2-binary
  cmd_prefix bash -c "cd pulpcore; pip install -r doc_requirements.txt"
fi
echo ::group::SSL
# Copy pulp CA
sudo docker cp pulp:/etc/pulp/certs/pulp_webserver.crt /usr/local/share/ca-certificates/pulp_webserver.crt

# Hack: adding pulp CA to certifi.where()
CERTIFI=$(python -c 'import certifi; print(certifi.where())')
cat /usr/local/share/ca-certificates/pulp_webserver.crt | sudo tee -a "$CERTIFI" > /dev/null
if [[ "$TEST" = "azure" ]]; then
  cat /usr/local/share/ca-certificates/azcert.crt | sudo tee -a "$CERTIFI" > /dev/null
fi

# Hack: adding pulp CA to default CA file
CERT=$(python -c 'import ssl; print(ssl.get_default_verify_paths().openssl_cafile)')
cat "$CERTIFI" | sudo tee -a "$CERT" > /dev/null

# Updating certs
sudo update-ca-certificates
echo ::endgroup::

if [[ "$TEST" = "azure" ]]; then
  AZCERTIFI=$(/opt/az/bin/python3 -c 'import certifi; print(certifi.where())')
  cat /usr/local/share/ca-certificates/azcert.crt >> $AZCERTIFI
  cat /usr/local/share/ca-certificates/azcert.crt | cmd_stdin_prefix tee -a /usr/local/lib/python3.8/site-packages/certifi/cacert.pem > /dev/null
  cat /usr/local/share/ca-certificates/azcert.crt | cmd_stdin_prefix tee -a /etc/pki/tls/cert.pem > /dev/null
  AZURE_STORAGE_CONNECTION_STRING='DefaultEndpointsProtocol=https;AccountName=devstoreaccount1;AccountKey=Eby8vdM02xNOcqFlqUwJPLlmEtlCDXJ1OUzFT50uSRZ6IFsuFq2UVErCz4I6tq/K1SZFPTOtr/KBHBeksoGMGw==;BlobEndpoint=https://ci-azurite:10000/devstoreaccount1;'
  az storage container create --name pulp-test --connection-string $AZURE_STORAGE_CONNECTION_STRING
fi

echo ::group::PIP_LIST
cmd_prefix bash -c "pip3 list && pip3 install pipdeptree && pipdeptree"
echo ::endgroup::
