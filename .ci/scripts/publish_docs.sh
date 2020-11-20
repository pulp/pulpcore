#!/bin/bash

set -euv

openssl aes-256-cbc -K $encrypted_d1a778bda808_key -iv $encrypted_d1a778bda808_iv -in .ci/assets/pulp-infra.enc -out ~/.ssh/pulp-infra -d
sudo chmod 600 ~/.ssh/pulp-infra

echo "docs.pulpproject.org,8.43.85.236 ecdsa-sha2-nistp256 AAAAE2VjZHNhLXNoYTItbmlzdHAyNTYAAAAIbmlzdHAyNTYAAABBBGXG+8vjSQvnAkq33i0XWgpSrbco3rRqNZr0SfVeiqFI7RN/VznwXMioDDhc+hQtgVhd6TYBOrV07IMcKj+FAzg=" >> /home/runner/.ssh/known_hosts
chmod 644 /home/runner/.ssh/known_hosts

pip3 install -r doc_requirements.txt

export PYTHONUNBUFFERED=1
export DJANGO_SETTINGS_MODULE=pulpcore.app.settings
export PULP_SETTINGS=$GITHUB_WORKSPACE/.ci/ansible/settings/settings.py

eval "$(ssh-agent -s)" #start the ssh agent
ssh-add ~/.ssh/pulp-infra

python3 .ci/scripts/docs-builder.py --build-type $1 --branch $2
