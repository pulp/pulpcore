#!/bin/bash

cd containers

# FIXME: This won't work  because not only is it outside the Docker build env,
# it's outside of the build context (the pwd from which `docker build` is run.)
# We need to find/develop a Dockerfile COPY solution for this.
: '
if [ -n "$PULP_PLUGIN_PR_NUMBER" ]; then
  PULPCORE_PLUGIN_PATH=../../pulpcore-plugin
else
  PULPCORE_PLUGIN_PATH=git+https://github.com/pulp/pulpcore-plugin.git
fi
cat > vars/vars.yaml << VARSYAML
---
images:
  - pulpcore_$(git rev-parse --abbrev-ref HEAD | tr '-' '_'):
      image_name: pulpcore
      tag: $(git rev-parse --abbrev-ref HEAD)
      pulpcore: ..
      pulpcore_plugin: $PULPCORE_PLUGIN_PATH
VARSYAML
'

cat > vars/vars.yaml << VARSYAML
---
images:
  - pulpcore_$(git rev-parse --abbrev-ref HEAD | tr '-' '_'):
      image_name: pulpcore
      tag: $(git rev-parse --abbrev-ref HEAD)
VARSYAML

ansible-playbook build.yaml
