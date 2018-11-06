# Pulp 3 Containers

This directory contains assets and tooling for building Pulp 3 container images. The current image is an all-in-one image with different runtime scripts to assume each of the roles: pulp-core, pulp-worker and pulp-resource-manager.

## Build

The base image can be built with the help of an Ansible script. To build the base image:

    ansible-playbook build.yaml

The image can be customized to include any number of plugins as a build argument:

    ansible-playbook build.yaml -e '{"plugins": ["pulp_file", "pulp_ansible"]}'

## Push Image to Registry

The built image can be pushed to a registry using an Ansible playbook. The default configuration will attempt to push the image to `quay.io/pulp`:

    ansible-playbook push.yaml

The image can be pushed to custom registry by specifying variables via the command line:

    ansible-playbook push.yaml -e registry=docker.io -e project=myproject
