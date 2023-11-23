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

mkdir ~/.ssh
touch ~/.ssh/pulp-infra
chmod 600 ~/.ssh/pulp-infra
echo "$PULP_DOCS_KEY" > ~/.ssh/pulp-infra

echo "docs.pulpproject.org,8.43.85.236 ecdsa-sha2-nistp256 AAAAE2VjZHNhLXNoYTItbmlzdHAyNTYAAAAIbmlzdHAyNTYAAABBBGXG+8vjSQvnAkq33i0XWgpSrbco3rRqNZr0SfVeiqFI7RN/VznwXMioDDhc+hQtgVhd6TYBOrV07IMcKj+FAzg=" >> ~/.ssh/known_hosts
chmod 644 ~/.ssh/known_hosts

pip3 install packaging

export PYTHONUNBUFFERED=1
export DJANGO_SETTINGS_MODULE=pulpcore.app.settings
export PULP_SETTINGS=$PWD/.ci/ansible/settings/settings.py
export WORKSPACE=$PWD

# start the ssh agent
eval "$(ssh-agent -s)"
ssh-add ~/.ssh/pulp-infra

python3 .github/workflows/scripts/docs-publisher.py --build-type "$1" --branch "$2"

if [[ "$GITHUB_WORKFLOW" == "Core changelog update" ]]; then
  # Do not build bindings docs on changelog update
  exit
fi

pip install mkdocs pymdown-extensions "Jinja2<3.1"

mkdir -p ../core-bindings
tar -xvf core-python-client-docs.tar --directory ../core-bindings
pushd ../core-bindings
cat >> mkdocs.yml << DOCSYAML
---
site_name: Pulpcore Client
site_description: Core bindings
site_author: Pulp Team
site_url: https://docs.pulpproject.org/pulpcore_client/
repo_name: pulp/pulpcore
repo_url: https://github.com/pulp/pulpcore
theme: readthedocs
DOCSYAML

# Building the bindings docs
mkdocs build

# publish to docs.pulpproject.org/pulpcore_client
rsync -avzh site/ doc_builder_pulpcore@docs.pulpproject.org:/var/www/docs.pulpproject.org/pulpcore_client/

# publish to docs.pulpproject.org/pulpcore_client/en/{release}
rsync -avzh site/ doc_builder_pulpcore@docs.pulpproject.org:/var/www/docs.pulpproject.org/pulpcore_client/en/"$2"
popd

mkdir -p ../file-bindings
tar -xvf file-python-client-docs.tar --directory ../file-bindings
pushd ../file-bindings
cat >> mkdocs.yml << DOCSYAML
---
site_name: PulpFile Client
site_description: File bindings
site_author: Pulp Team
site_url: https://docs.pulpproject.org/pulp_file_client/
repo_name: pulp/pulp_file
repo_url: https://github.com/pulp/pulp_file
theme: readthedocs
DOCSYAML

# Building the bindings docs
mkdocs build

# publish to docs.pulpproject.org/pulp_file_client
rsync -avzh site/ doc_builder_pulp_file@docs.pulpproject.org:/var/www/docs.pulpproject.org/pulp_file_client/

# publish to docs.pulpproject.org/pulp_file_client/en/{release}
rsync -avzh site/ doc_builder_pulp_file@docs.pulpproject.org:/var/www/docs.pulpproject.org/pulp_file_client/en/"$2"
popd
