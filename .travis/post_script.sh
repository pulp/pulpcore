#!/bin/bash

# Travis doesn't always name it "pulpcore"
PULPCORE_PATH=./$(basename $PWD)

cd containers

# If we are on a PR
if [ -n "$TRAVIS_PULL_REQUEST_BRANCH" ]; then
  TAG=$TRAVIS_PULL_REQUEST_BRANCH
# For push builds, tag builds, and hopefully cron builds
elif [ -n "$TRAVIS_BRANCH" ]; then
  TAG=$TRAVIS_BRANCH
  if [[ "$IMAGE_KEY" = "master" ]]; then
    TAG=latest
  fi
else
  # Fallback
  TAG=$(git rev-parse --abbrev-ref HEAD)
fi
# Ansible var names/keys cannot have dashes
TAG=$(echo $TAG | tr '-' '_')

if [ -n "$PULP_PLUGIN_PR_NUMBER" ]; then
  PULPCORE_PLUGIN_PATH=./pulpcore-plugin
else
  PULPCORE_PLUGIN_PATH=git+https://github.com/pulp/pulpcore-plugin.git
fi

cat > vars/vars.yaml << VARSYAML
---
images:
  - pulpcore_$TAG:
      image_name: pulpcore
      tag: $TAG
      pulpcore: $PULPCORE_PATH
      pulpcore_plugin: $PULPCORE_PLUGIN_PATH
VARSYAML

# ansible-playbook build.yaml
