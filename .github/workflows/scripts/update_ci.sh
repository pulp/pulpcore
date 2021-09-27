#!/usr/bin/env bash

set -eu

if [ ! -d ../plugin_template ]; then
  echo "Checking out plugin_template"
  git clone https://github.com/pulp/plugin_template.git ../plugin_template
fi


if [ ! -f "template_config.yml" ]; then
  echo "No template_config.yml detected."
  exit 1
fi

pushd ../plugin_template
./plugin-template --github pulpcore
popd

# Check if only gitref file has changed, so no effect on CI workflows.
if [[ `git diff --name-only` == ".github/template_gitref" ]]; then
  echo "CI update has no effect on workflows, skipping PR creation."
  git stash
  exit 0
fi

if [[ `git status --porcelain` ]]; then
  git add -A
  git commit -m "Update CI files" -m "[noissue]"
else
  echo "No updates needed"
fi
